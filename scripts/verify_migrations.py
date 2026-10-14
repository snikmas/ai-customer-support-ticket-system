"""Verify supported migrations against empty and populated databases.

F07 requires the migration paths to be exercised, not just that ``alembic
upgrade head`` prints no error:

* an empty PostgreSQL 16 database reaches head with the expected columns and
  indexes, and
* a synthetic "pre-repair" PostgreSQL 16 database at the previous head, holding
  PENDING, RUNNING, and terminal analysis rows, upgrades without losing data and
  leaves recovery following policy.

Both targets are created and dropped by this run (see ``src.tests.pg_target``),
so it never touches a shared database. The SQLite initialization/upgrade path is
covered by ``src/tests/test_analysis_recovery.py``.

Usage:
    TEST_POSTGRES_URL=postgresql+psycopg://user:pw@host:port/postgres \
    TEST_POSTGRES_ALLOW_DESTRUCTIVE=1 \
    myvenv/bin/python scripts/verify_migrations.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import operations  # noqa: E402

PREVIOUS_HEAD = "b2c3d4e5f6a7"
HEAD = "c3d4e5f6a7b8"


def _alembic(env: dict[str, str], *args: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed:\n{completed.stdout}")


def _migration_env(database_url: str) -> dict[str, str]:
    env = {**os.environ}
    env["DATABASE_URL"] = database_url
    env["PYTHON_DOTENV_DISABLED"] = "1"
    env["REDIS_ENABLED"] = "false"
    return env


def _verify_empty_database(database_url: str) -> dict:
    env = _migration_env(database_url)
    _alembic(env, "upgrade", "head")
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "tickets" in tables and "analysis_result" in tables, tables
        columns = {c["name"] for c in inspector.get_columns("analysis_result")}
        assert {
            "execution_id",
            "lease_expires_at",
            "dispatch_count",
            "reconciliation_attempted_at",
        } <= columns, columns
        indexes = {i["name"] for i in inspector.get_indexes("analysis_result")}
        assert "ix_analysis_result_reconciliation_scan" in indexes, indexes
    finally:
        engine.dispose()
    return {
        "path": "empty->head",
        "revision": HEAD,
        "columns": sorted(columns),
        "indexes": sorted(indexes),
    }


def _seed_pre_repair(engine) -> None:
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)
    rows = [
        # PENDING: never started, no lease.
        ("pending-1", "PENDING", 0, None, None, None, None, None, now),
        # RUNNING with an expired lease: abandoned work recovery must reach it.
        ("running-1", "RUNNING", 1, past, None, None, None, None, past),
        # Terminal COMPLETED: must never be re-run.
        (
            "completed-1",
            "COMPLETED",
            1,
            past,
            "Already summarized",
            None,
            None,
            past,
            past,
        ),
        # Terminal FAILED: must never be re-run.
        (
            "failed-1",
            "FAILED",
            1,
            past,
            None,
            "provider_result_unknown",
            "interrupted",
            past,
            past,
        ),
    ]
    with engine.begin() as connection:
        for (
            row_id,
            status,
            attempts,
            started,
            summary,
            error_code,
            error_message,
            completed,
            updated,
        ) in rows:
            connection.execute(
                text(
                    "INSERT INTO analysis_result ("
                    "id, input_snapshot, summary, error_code, error_message, "
                    "ticket_id, job_id, requester_id, provider, model, "
                    "prompt_version, input_tokens, output_tokens, attempt_count, "
                    "dispatch_count, execution_id, lease_expires_at, "
                    "created_at, started_at, completed_at, updated_at, status"
                    ") VALUES ("
                    ":id, '{}', :summary, :error_code, :error_message, NULL, NULL, "
                    "NULL, NULL, NULL, NULL, NULL, NULL, :attempts, 0, "
                    ":execution_id, :lease, :created, :started, :completed, "
                    ":updated, :status)"
                ),
                {
                    "id": row_id,
                    "summary": summary,
                    "error_code": error_code,
                    "error_message": error_message,
                    "attempts": attempts,
                    "execution_id": "exec-" + row_id if status == "RUNNING" else None,
                    "lease": started,
                    "created": past,
                    "started": started,
                    "completed": completed,
                    "updated": updated,
                    "status": status,
                },
            )


def _verify_pre_repair_database(database_url: str) -> dict:
    env = _migration_env(database_url)
    _alembic(env, "upgrade", PREVIOUS_HEAD)
    engine = create_engine(database_url)
    try:
        _seed_pre_repair(engine)

        # Upgrade with existing data present.
        _alembic(env, "upgrade", "head")

        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("analysis_result")}
        assert "reconciliation_attempted_at" in columns, columns
        indexes = {i["name"] for i in inspector.get_indexes("analysis_result")}
        assert "ix_analysis_result_reconciliation_scan" in indexes, indexes

        with engine.connect() as connection:
            stored = {
                row.id: row
                for row in connection.execute(
                    text(
                        "SELECT id, status, summary, error_code, "
                        "reconciliation_attempted_at FROM analysis_result"
                    )
                )
            }
        assert stored["completed-1"].summary == "Already summarized"
        assert stored["failed-1"].error_code == "provider_result_unknown"
        assert all(
            row.reconciliation_attempted_at is None for row in stored.values()
        ), "existing rows must start as never-considered"

        # The application query must reach pending + abandoned running only.
        operations.engine = engine
        now = datetime.now(timezone.utc)
        reconcilable = {
            row.id for row in operations.get_reconcilable_analysis_results(50, now)
        }
        assert reconcilable == {"pending-1", "running-1"}, reconcilable
    finally:
        engine.dispose()
    return {
        "path": f"{PREVIOUS_HEAD}->head with data",
        "revision": HEAD,
        "preserved_rows": sorted(stored),
        "reconcilable": sorted(reconcilable),
        "left_marker_null": True,
    }


def main() -> int:
    from src.tests import pg_target

    base_url = os.getenv(pg_target.BASE_URL_ENV)
    if not base_url:
        print("COULD-NOT-RUN: TEST_POSTGRES_URL is not set")
        return 2
    try:
        pg_target.require_opt_in()
    except pg_target.UnsafeIntegrationTargetError as exc:
        print(f"COULD-NOT-RUN: {exc}")
        return 2

    token = f"migr_{os.getpid()}_{datetime.now(timezone.utc).strftime('%H%M%S')}"
    plan = pg_target.plan_task_owned_target(base_url, token=token)
    pg_target.create_task_owned_database(plan)
    results = []
    try:
        results.append(_verify_empty_database(plan.owned_url))
        # Fresh database for the populated path.
        pg_target.drop_task_owned_database(plan)
        pg_target.create_task_owned_database(plan)
        results.append(_verify_pre_repair_database(plan.owned_url))
    finally:
        pg_target.drop_task_owned_database(plan)

    evidence_dir = ROOT / ".project-workflow" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = evidence_dir / f"migrations-{stamp}.json"
    target.write_text(
        json.dumps(
            {"generated_at": datetime.now(timezone.utc).isoformat(), "results": results},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for result in results:
        print(f"PASS: {result['path']}")
    print(f"Evidence: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
