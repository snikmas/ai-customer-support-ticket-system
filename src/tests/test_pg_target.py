"""Isolation and rejection checks for task-owned PostgreSQL integration targets.

These run without a server: they prove that a wrong or inherited target is
rejected by configuration alone, and that the run derives its own database name
instead of trusting the configured one. The live disposal path is exercised by
the ``mutation_engine`` PostgreSQL variant when ``TEST_POSTGRES_URL`` and
``TEST_POSTGRES_ALLOW_DESTRUCTIVE=1`` are set.
"""

import pytest

from src.tests import pg_target
from src.tests.pg_target import UnsafeIntegrationTargetError


def test_opt_in_is_required_before_any_connection(monkeypatch):
    monkeypatch.delenv(pg_target.OPT_IN_ENV, raising=False)
    with pytest.raises(UnsafeIntegrationTargetError):
        pg_target.require_opt_in({})

    # Explicit opt-in passes the gate.
    pg_target.require_opt_in({pg_target.OPT_IN_ENV: "1"})


def test_plan_rejects_a_non_postgres_url():
    with pytest.raises(UnsafeIntegrationTargetError):
        pg_target.plan_task_owned_target("sqlite+pysqlite:///tmp/x.db", token="run1")


def test_plan_rejects_a_url_without_a_database():
    with pytest.raises(UnsafeIntegrationTargetError):
        pg_target.plan_task_owned_target(
            "postgresql+psycopg://user:secret@db.internal", token="run1"
        )


def test_plan_derives_a_run_owned_database_not_the_configured_one():
    plan = pg_target.plan_task_owned_target(
        "postgresql+psycopg://postgres:resolve@127.0.0.1:5432/tickets_test",
        token="run-abc123",
    )
    assert plan.database.startswith("resolveai_test_")
    assert plan.database != "tickets_test"
    assert "run_abc123" in plan.database
    # The owned URL points at the derived database, never the anchor database.
    assert plan.owned_url.endswith(f"/{plan.database}")


def test_token_is_sanitized_into_a_safe_identifier():
    name = pg_target.task_owned_database_name("Run-2026:10/13 A")
    assert name == "resolveai_test_run_2026_10_13_a"
    with pytest.raises(UnsafeIntegrationTargetError):
        pg_target.task_owned_database_name("///")


def test_rejection_happens_without_contacting_any_service(monkeypatch):
    """A rejected target must fail before opening a connection."""
    calls = []

    def _forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("no connection may be opened for a rejected target")

    monkeypatch.setattr(pg_target, "create_engine", _forbidden)

    with pytest.raises(UnsafeIntegrationTargetError):
        pg_target.plan_task_owned_target("mysql://user@db/db", token="run1")
    with pytest.raises(UnsafeIntegrationTargetError):
        pg_target.require_opt_in({"TEST_POSTGRES_ALLOW_DESTRUCTIVE": "0"})

    assert calls == []
