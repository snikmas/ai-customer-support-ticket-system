"""Run safe, repeatable ResolveAI release checks and write redacted evidence.

The default run is local and does not start services, contact providers, read
secret files, or modify the database. Opt-in runtime checks are deliberately
separate so a normal verification run cannot create external spend.

Every check runs in a controlled environment: python-dotenv loading is disabled
(so ``src/core/config.py`` never reads a developer's private ``.env``), Redis is
off, the analyzer provider is the local fake, and the database and attachment
storage point at a disposable temporary directory. Frontend commands ignore
inherited ``VITE_*`` values and user-level npm configuration so a local build
cannot silently pick up private developer settings.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / ".project-workflow" / "evidence"
SECRET_PATTERN = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+|api[_-]?key\s*[:=]\s*|"
    r"refresh[_-]?token[_-]?secret\s*[:=]\s*)[^\s,;]+"
)

# Per-check wall-clock bound. A hung test run, build, or network client must not
# block verification forever.
DEFAULT_TIMEOUT_SECONDS = 900

CHECK_PASS = "pass"
CHECK_FAIL = "fail"
CHECK_COULD_NOT_RUN = "could-not-run"

# Provider credentials removed from the controlled environment. The fake
# analyzer does not need them, and their presence would let a check accidentally
# reach an external provider.
SECRET_ENV_KEYS = (
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "REFRESH_TOKEN_SECRET",
)

# Integration-target overrides removed from the controlled environment. A
# developer shell may export a real (or remote) PostgreSQL/Redis target for the
# opt-in integration suites; the default release check must never inherit it,
# because the PostgreSQL fixture runs ``Base.metadata.drop_all`` before tests.
INTEGRATION_TARGET_ENV_KEYS = (
    "TEST_POSTGRES_URL",
    "REDIS_URL",
    "SMOKE_REDIS_URL",
    "SMOKE_DATABASE_URL",
    "SMOKE_ALLOW_REMOTE",
    "SMOKE_KEEP_DATABASE",
)

_GIT_REVISION: str | None = None


@dataclass(frozen=True)
class Workspace:
    """Disposable paths and files used to isolate a verification run."""

    root: Path
    database_url: str
    attachments_dir: Path
    npm_userconfig: Path


@dataclass
class Check:
    name: str
    command: list[str]
    scope: str
    status: str
    returncode: int | None
    reason: str | None
    git_revision: str
    output_tail: str


def redact(text: str) -> str:
    return SECRET_PATTERN.sub(r"\1<redacted>", text)


def current_git_revision() -> str:
    """Return the tested revision, or ``unknown`` outside a usable git tree."""
    global _GIT_REVISION
    if _GIT_REVISION is not None:
        return _GIT_REVISION
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        _GIT_REVISION = "unknown"
        return _GIT_REVISION
    _GIT_REVISION = completed.stdout.strip() if completed.returncode == 0 else "unknown"
    return _GIT_REVISION


def make_workspace(root: Path) -> Workspace:
    """Create disposable database, storage, and npm-config locations."""
    root.mkdir(parents=True, exist_ok=True)
    attachments_dir = root / "uploads"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    npm_userconfig = root / "npmrc"
    npm_userconfig.write_text("", encoding="utf-8")
    return Workspace(
        root=root,
        database_url=f"sqlite+pysqlite:///{root / 'verify-release.db'}",
        attachments_dir=attachments_dir,
        npm_userconfig=npm_userconfig,
    )


def controlled_env(workspace: Workspace) -> dict[str, str]:
    """Build an environment that cannot depend on private developer state.

    Variable names and reasons:

    - ``PYTHON_DOTENV_DISABLED=1``: ``src/core/config.py:6`` calls
      ``load_dotenv(PROJECT_ROOT / ".env")``; python-dotenv 1.2.2 skips loading
      when this variable is truthy (``dotenv/main.py:22-29,412``).
    - ``REDIS_ENABLED=false``: ``src/core/config.py:20`` reads it; the suite is
      meant to run without Redis.
    - ``DATABASE_URL``: ``src/core/config.py:9``; pointed at disposable SQLite.
    - ``ATTACHMENTS_DIR``: ``src/core/config.py:55``; pointed at disposable
      storage so uploads never touch the real ``uploads/`` directory.
    - ``ANALYZER_PROVIDER=fake``: ``src/core/config.py:49``; avoids provider
      credentials and external calls.
    - ``FAKE_ANALYZER_DELAY_SECONDS`` / ``FAKE_ANALYZER_FAILURE_MODE``:
      ``src/analyzers/fake.py:67-68``; deterministic fake behavior.
    - ``DATABASE_ECHO=false``: ``src/core/config.py:13``; quiet SQL logging.
    - ``NPM_CONFIG_USERCONFIG``: an empty file instead of a developer's
      ``~/.npmrc``, so private registry/auth overrides are not used.
    - ``VITE_VERIFY_DISABLE_ENV_FILES=1``: read by ``site/vite.config.ts`` to
      set ``envDir: false``, which disables Vite ``.env`` file loading.
    - ``INTEGRATION_TARGET_ENV_KEYS``: ``TEST_POSTGRES_URL``, ``REDIS_URL``, and
      the ``SMOKE_*`` overrides are removed so a normal check cannot be
      redirected at an inherited external database or Redis instance.
    """
    env = os.environ.copy()

    env["PYTHON_DOTENV_DISABLED"] = "1"
    env["REDIS_ENABLED"] = "false"
    env["DATABASE_ECHO"] = "false"
    env["ANALYZER_PROVIDER"] = "fake"
    env["FAKE_ANALYZER_DELAY_SECONDS"] = "0"
    env["FAKE_ANALYZER_FAILURE_MODE"] = "none"
    env["DATABASE_URL"] = workspace.database_url
    env["ATTACHMENTS_DIR"] = str(workspace.attachments_dir)

    for key in SECRET_ENV_KEYS:
        env.pop(key, None)
    for key in INTEGRATION_TARGET_ENV_KEYS:
        env.pop(key, None)
    for key in [key for key in env if key.startswith("VITE_")]:
        env.pop(key, None)

    env["NPM_CONFIG_USERCONFIG"] = str(workspace.npm_userconfig)
    env["VITE_VERIFY_DISABLE_ENV_FILES"] = "1"
    return env


def run_check(
    name: str,
    command: list[str],
    *,
    scope: str,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int | float = DEFAULT_TIMEOUT_SECONDS,
) -> Check:
    revision = current_git_revision()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return Check(
            name,
            command,
            scope,
            CHECK_COULD_NOT_RUN,
            None,
            f"timed out after {timeout}s",
            revision,
            redact(partial)[-4000:],
        )
    except FileNotFoundError as exc:
        return Check(
            name,
            command,
            scope,
            CHECK_COULD_NOT_RUN,
            None,
            f"command not found: {exc.filename or command[0]}",
            revision,
            "",
        )
    except OSError as exc:
        return Check(
            name,
            command,
            scope,
            CHECK_COULD_NOT_RUN,
            None,
            f"could not start command: {exc}",
            revision,
            "",
        )

    output = redact(completed.stdout or "")
    status = CHECK_PASS if completed.returncode == 0 else CHECK_FAIL
    return Check(name, command, scope, status, completed.returncode, None, revision, output[-4000:])


def default_checks(env: dict[str, str]) -> list[Check]:
    return [
        run_check(
            "backend tests (isolated: no dotenv, Redis off, fake provider)",
            ["myvenv/bin/python", "-m", "pytest", "-q"],
            scope="backend",
            env=env,
            timeout=900,
        ),
        run_check(
            "ruff syntax and undefined-name checks",
            [
                "myvenv/bin/ruff",
                "check",
                "main.py",
                "src",
                "scripts",
                "bootstrap_superadmin.py",
            ],
            scope="repository",
            env=env,
            timeout=300,
        ),
        run_check(
            "Python compilation",
            [
                "myvenv/bin/python",
                "-m",
                "compileall",
                "-q",
                "main.py",
                "src",
                "scripts",
                "bootstrap_superadmin.py",
            ],
            scope="backend",
            env=env,
            timeout=300,
        ),
        run_check(
            "frontend tests",
            ["npm", "test", "--", "--run"],
            cwd=ROOT / "site",
            scope="frontend",
            env=env,
            timeout=900,
        ),
        run_check(
            "frontend production build",
            ["npm", "run", "build"],
            cwd=ROOT / "site",
            scope="frontend",
            env=env,
            timeout=600,
        ),
        run_check("git whitespace check", ["git", "diff", "--check"], scope="repository", env=env, timeout=120),
    ]


def runtime_checks(*, compose: bool, env: dict[str, str]) -> list[Check]:
    if not compose:
        return []
    return [
        run_check("compose service status", ["docker", "compose", "ps"], scope="runtime", env=env, timeout=60),
        run_check(
            "API health endpoint",
            [
                "myvenv/bin/python",
                "-c",
                (
                    "import urllib.request; "
                    "opener = urllib.request.build_opener(urllib.request.ProxyHandler({})); "
                    "opener.open("
                    "'http://127.0.0.1:8000/health', timeout=5"
                    ").read()"
                ),
            ],
            scope="runtime",
            env=env,
            timeout=60,
        ),
    ]


def write_evidence(checks: list[Check]) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = EVIDENCE_DIR / f"verify-release-{stamp}.json"
    target.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "root": str(ROOT),
                "git_revision": current_git_revision(),
                "checks": [asdict(check) for check in checks],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compose",
        action="store_true",
        help="also inspect the already-running Compose stack and API health",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="resolveai-verify-") as tmp:
        workspace = make_workspace(Path(tmp))
        env = controlled_env(workspace)
        checks = default_checks(env) + runtime_checks(compose=args.compose, env=env)
        evidence = write_evidence(checks)

    for check in checks:
        if check.status == CHECK_PASS:
            print(f"PASS: {check.name}")
        elif check.status == CHECK_FAIL:
            print(f"FAIL: {check.name} (exit {check.returncode})")
        else:
            print(f"COULD-NOT-RUN: {check.name} ({check.reason})")
    print(f"Evidence: {evidence}")
    return 0 if all(check.status == CHECK_PASS for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
