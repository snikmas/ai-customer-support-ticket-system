"""Run safe, repeatable ResolveAI release checks and write redacted evidence.

The default run is local and does not start services, contact providers, read
secret files, or modify the database. Opt-in runtime checks are deliberately
separate so a normal verification run cannot create external spend.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / ".project-workflow" / "evidence"
SECRET_PATTERN = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+|api[_-]?key\s*[:=]\s*|"
    r"refresh[_-]?token[_-]?secret\s*[:=]\s*)[^\s,;]+"
)


@dataclass
class Check:
    name: str
    command: list[str]
    returncode: int
    output_tail: str


def redact(text: str) -> str:
    return SECRET_PATTERN.sub(r"\1<redacted>", text)


def run_check(
    name: str,
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> Check:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = redact(completed.stdout or "")
    return Check(name, command, completed.returncode, output[-4000:])


def default_checks() -> list[Check]:
    test_env = os.environ.copy()
    test_env["REDIS_ENABLED"] = "false"
    return [
        run_check(
            "backend tests (Redis disabled and isolated)",
            ["myvenv/bin/python", "-m", "pytest", "-q"],
            env=test_env,
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
        ),
        run_check("frontend tests", ["npm", "test", "--", "--run"], cwd=ROOT / "site"),
        run_check("frontend production build", ["npm", "run", "build"], cwd=ROOT / "site"),
        run_check("git whitespace check", ["git", "diff", "--check"]),
    ]


def runtime_checks(*, compose: bool) -> list[Check]:
    if not compose:
        return []
    return [
        run_check("compose service status", ["docker", "compose", "ps"]),
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

    checks = default_checks() + runtime_checks(compose=args.compose)
    evidence = write_evidence(checks)
    for check in checks:
        state = "PASS" if check.returncode == 0 else "FAIL"
        print(f"{state}: {check.name}")
    print(f"Evidence: {evidence}")
    return 0 if all(check.returncode == 0 for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
