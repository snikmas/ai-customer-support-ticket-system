"""Obsolete-ownership transitions for interrupted analysis on both engines.

F06 requires the obsolete-analysis-ownership cases to execute on SQLite and
PostgreSQL 16, not only SQLite. These tests use the shared ``mutation_engine``
fixture (both engines) with rows that carry no ticket/user foreign keys, so no
extra seed data is needed and no Redis is used.
"""

from datetime import datetime, timedelta, timezone

from src import constants
from src.db import operations
from src.jobs import service as jobs_service
from src.tests.test_analysis_recovery import pending_result


def _row(engine, result_id="result-1"):
    return operations.create_analysis_result(
        pending_result(result_id=result_id, ticket_id=None, requester_id=None)
    )


def test_obsolete_completion_is_rejected_on_both_engines(mutation_engine):
    row = _row(mutation_engine, "result-1")
    t0 = datetime.now(timezone.utc)

    first = operations.start_analysis_attempt(row.id, t0, lease_seconds=60)
    assert operations.return_analysis_to_pending(
        row.id, t0 + timedelta(seconds=1), execution_id=first.execution_id
    ) is not None
    second = operations.start_analysis_attempt(
        row.id, t0 + timedelta(seconds=2), lease_seconds=60
    )
    assert second.execution_id != first.execution_id

    assert operations.complete_analysis_result(
        row.id,
        "obsolete execution result",
        t0 + timedelta(seconds=3),
        execution_id=first.execution_id,
    ) is None
    stored = operations.complete_analysis_result(
        row.id,
        "current execution result",
        t0 + timedelta(seconds=3),
        execution_id=second.execution_id,
    )
    assert stored is not None
    assert stored.summary == "current execution result"


def test_stale_reconciler_cannot_fail_a_newer_attempt_on_both_engines(
    mutation_engine,
):
    row = _row(mutation_engine, "result-2")
    t0 = datetime.now(timezone.utc)

    first = operations.start_analysis_attempt(row.id, t0, lease_seconds=0)
    stale_snapshot = operations.get_analysis_result(row.id)
    assert stale_snapshot.execution_id == first.execution_id

    assert operations.return_analysis_to_pending(
        row.id, t0 + timedelta(seconds=1), execution_id=first.execution_id
    ) is not None
    second = operations.start_analysis_attempt(
        row.id, t0 + timedelta(seconds=2), lease_seconds=600
    )

    assert (
        jobs_service._reconcile_abandoned_analysis(
            stale_snapshot, t0 + timedelta(seconds=3)
        )
        == "skipped"
    )
    stored = operations.get_analysis_result(row.id)
    assert stored.status is constants.AnalysisStatus.RUNNING
    assert stored.execution_id == second.execution_id


def test_provider_attempt_budget_is_enforced_on_both_engines(mutation_engine):
    row = _row(mutation_engine, "result-3")
    t0 = datetime.now(timezone.utc)

    first = operations.start_analysis_attempt(row.id, t0, lease_seconds=60)
    assert operations.return_analysis_to_pending(
        row.id, t0 + timedelta(seconds=1), execution_id=first.execution_id
    ) is not None
    second = operations.start_analysis_attempt(
        row.id, t0 + timedelta(seconds=2), lease_seconds=60
    )
    assert operations.return_analysis_to_pending(
        row.id, t0 + timedelta(seconds=3), execution_id=second.execution_id
    ) is not None
    third = operations.start_analysis_attempt(
        row.id, t0 + timedelta(seconds=4), lease_seconds=60
    )
    assert third is not None
    assert operations.get_analysis_result(row.id).attempt_count == 3

    # The provider budget is exhausted; a fourth attempt must be refused.
    assert (
        operations.start_analysis_attempt(
            row.id, t0 + timedelta(seconds=5), lease_seconds=60
        )
        is None
    )
