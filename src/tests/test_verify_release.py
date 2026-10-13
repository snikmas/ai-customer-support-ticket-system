"""Isolation and safety checks for the release verifier.

These tests exercise ``scripts/verify_release.py`` directly. They never read a
real private ``.env`` or key file: the sentinel case writes a synthetic dotenv
into a temporary directory and proves the verifier's controlled environment
prevents python-dotenv from loading it.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_release.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_release_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


def test_controlled_env_does_not_load_synthetic_sentinel_dotenv(tmp_path):
    sentinel_dir = tmp_path / "leaky"
    sentinel_dir.mkdir()
    (sentinel_dir / ".env").write_text(
        "VERIFY_RELEASE_SENTINEL=leaked-sentinel-value\n",
        encoding="utf-8",
    )

    workspace = verifier.make_workspace(tmp_path / "workspace")
    env = verifier.controlled_env(workspace)
    assert env["PYTHON_DOTENV_DISABLED"] == "1"

    script = (
        "import os\n"
        "from pathlib import Path\n"
        "from dotenv import load_dotenv\n"
        "load_dotenv(Path.cwd() / '.env')\n"
        "print('SENTINEL=' + str(os.getenv('VERIFY_RELEASE_SENTINEL')))\n"
    )
    check = verifier.run_check(
        "sentinel dotenv isolation",
        [sys.executable, "-c", script],
        scope="test",
        cwd=sentinel_dir,
        env=env,
        timeout=30,
    )

    assert check.status == verifier.CHECK_PASS
    assert "SENTINEL=None" in check.output_tail
    assert "leaked-sentinel-value" not in check.output_tail


def test_controlled_env_replaces_private_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://private-host/private-db")
    monkeypatch.setenv("OPENROUTER_API_KEY", "leaked-provider-key")
    monkeypatch.setenv("VITE_API_BASE_URL", "http://private.example/api")

    workspace = verifier.make_workspace(tmp_path)
    env = verifier.controlled_env(workspace)

    assert env["PYTHON_DOTENV_DISABLED"] == "1"
    assert env["REDIS_ENABLED"] == "false"
    assert env["ANALYZER_PROVIDER"] == "fake"
    assert env["DATABASE_URL"] == workspace.database_url
    assert env["DATABASE_URL"].startswith("sqlite+pysqlite:///")
    assert str(workspace.root) in env["DATABASE_URL"]
    assert env["ATTACHMENTS_DIR"] == str(workspace.attachments_dir)
    assert str(workspace.root) in env["ATTACHMENTS_DIR"]
    assert "OPENROUTER_API_KEY" not in env
    assert env["NPM_CONFIG_USERCONFIG"] == str(workspace.npm_userconfig)
    assert env["VITE_VERIFY_DISABLE_ENV_FILES"] == "1"
    assert not [
        key
        for key in env
        if key.startswith("VITE_") and key != "VITE_VERIFY_DISABLE_ENV_FILES"
    ], "inherited VITE_ variables must not reach the frontend build"


def test_controlled_env_strips_integration_target_overrides(monkeypatch, tmp_path):
    # A developer shell may export an external PostgreSQL/Redis target for the
    # opt-in integration suites. The default check must not inherit it, because
    # the PostgreSQL fixture calls ``Base.metadata.drop_all``.
    monkeypatch.setenv(
        "TEST_POSTGRES_URL", "postgresql+psycopg://real-host/real-db"
    )
    monkeypatch.setenv("REDIS_URL", "redis://real-host:6379/0")
    monkeypatch.setenv("SMOKE_REDIS_URL", "redis://real-host:6379/1")
    monkeypatch.setenv("SMOKE_DATABASE_URL", "postgresql://real-host/real-db")

    workspace = verifier.make_workspace(tmp_path)
    env = verifier.controlled_env(workspace)

    for key in (
        "TEST_POSTGRES_URL",
        "REDIS_URL",
        "SMOKE_REDIS_URL",
        "SMOKE_DATABASE_URL",
    ):
        assert key not in env, f"{key} must not reach the default check"


def test_run_check_distinguishes_failure_from_could_not_run(tmp_path):
    workspace = verifier.make_workspace(tmp_path)
    env = verifier.controlled_env(workspace)

    passed = verifier.run_check(
        "ok", [sys.executable, "-c", "print('ok')"], scope="backend", env=env, timeout=30
    )
    assert passed.status == verifier.CHECK_PASS
    assert passed.returncode == 0
    assert passed.reason is None
    assert passed.scope == "backend"
    # A git checkout records a 40-hex revision; a source package with no .git
    # records "unknown". Both are valid; the test only rejects a crash value.
    assert re.fullmatch(r"[0-9a-f]{40}", passed.git_revision) or (
        passed.git_revision == "unknown"
    )

    failed = verifier.run_check(
        "fail",
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        scope="backend",
        env=env,
        timeout=30,
    )
    assert failed.status == verifier.CHECK_FAIL
    assert failed.returncode == 3
    assert failed.reason is None

    missing = verifier.run_check(
        "missing",
        ["definitely-not-a-real-command-for-verify-release"],
        scope="repository",
        env=env,
        timeout=30,
    )
    assert missing.status == verifier.CHECK_COULD_NOT_RUN
    assert missing.returncode is None
    assert "not found" in missing.reason

    timed_out = verifier.run_check(
        "timeout",
        [sys.executable, "-c", "import time; time.sleep(5)"],
        scope="backend",
        env=env,
        timeout=0.5,
    )
    assert timed_out.status == verifier.CHECK_COULD_NOT_RUN
    assert timed_out.returncode is None
    assert "timed out" in timed_out.reason
