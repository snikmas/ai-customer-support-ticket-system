"""Phase E failure-injection regressions for interrupted AI analysis.

Every test uses a disposable SQLite database and a local fake queue/provider.
None of them touch Redis, PostgreSQL, or a real provider.

Policy under test: a provider call whose outcome is uncertain must reach an
explicit safe terminal state and wait for a human retry. Only work that clearly
has not started is recovered automatically.
"""

import threading
from datetime import datetime, timedelta, timezone

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from rq.exceptions import DuplicateJobError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from src import constants
from src.analyzers import AnalysisInputSnapshot, DeterministicFakeAnalyzer
from src.db import operations
from src.db.migrations import migrate_analysis_result_contract
from src.db.models import AnalysisResult as DbAnalysisResult
from src.db.models import Base, Ticket
from src.jobs import cron as jobs_cron
from src.jobs import service as jobs_service


@pytest.fixture
def recovery_engine(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'analysis-recovery.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(operations, "engine", engine)
    yield engine
    engine.dispose()


class FakeJob:
    def __init__(self, job_id, status="queued"):
        self.id = job_id
        self.status = status
        self.deleted = False

    def get_status(self, refresh=False):
        return self.status

    def delete(self):
        self.deleted = True
        self.status = "deleted"


class FakeQueue:
    """Minimal stand-in for an RQ Queue with a global lock.

    The lock models Redis's single-key uniqueness so concurrent reconcilers
    compete for the same stable job identity exactly like production.
    """

    def __init__(self, *, unavailable=False):
        self.jobs = {}
        self.enqueued = []
        self.unavailable = unavailable
        self._lock = threading.Lock()

    def fetch_job(self, job_id):
        if self.unavailable:
            raise RedisConnectionError("redis unavailable")
        with self._lock:
            return self.jobs.get(job_id)

    def enqueue(
        self,
        function,
        analysis_result_id,
        *,
        job_id=None,
        unique=False,
        **settings,
    ):
        if self.unavailable:
            raise RedisConnectionError("redis unavailable")
        with self._lock:
            existing = self.jobs.get(job_id)
            if (
                unique
                and existing is not None
                and existing.status in jobs_service.ANALYSIS_ACTIVE_JOB_STATUSES
            ):
                raise DuplicateJobError("analysis job already exists")
            job = FakeJob(job_id, "queued")
            self.jobs[job_id] = job
            self.enqueued.append(job_id)
            return job


def install_queue(monkeypatch, queue):
    monkeypatch.setattr(jobs_service, "get_ticket_jobs_queue", lambda: queue)


def add_ticket(engine, *, ticket_id="ticket-1"):
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add(Ticket(
            id=ticket_id,
            title="Payment failed",
            description="Card payment returns error 500",
            category=constants.Category.BILLING,
            tags=constants.serialize_tags([constants.Tag.ERROR_500]),
            department_id=None,
            assigned_agent_id="agent-1",
            creator_user_id="customer-1",
            status=constants.Status.IN_PROGRESS,
            priority=constants.Priority.HIGH,
            updated_at=now,
            created_at=now,
            due_at=None,
            deleted_at=None,
        ))
        session.commit()


def snapshot_json() -> str:
    return AnalysisInputSnapshot(
        title="Payment failed",
        description="Card payment returns error 500",
        category=constants.Category.BILLING,
        tags=(constants.Tag.ERROR_500,),
        priority=constants.Priority.HIGH,
        status=constants.Status.IN_PROGRESS,
    ).model_dump_json()


def pending_result(
    *,
    result_id="result-1",
    ticket_id="ticket-1",
    requester_id="agent-1",
    provider="fake",
    model="deterministic-fake-v1",
    prompt_version="ticket_summary_v1",
    now=None,
):
    now = now or datetime.now(timezone.utc)
    return DbAnalysisResult(
        id=result_id,
        input_snapshot=snapshot_json(),
        summary=None,
        error_code=None,
        error_message=None,
        ticket_id=ticket_id,
        job_id=None,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_tokens=None,
        output_tokens=None,
        requester_id=requester_id,
        attempt_count=0,
        created_at=now,
        started_at=None,
        completed_at=None,
        updated_at=now,
        status=constants.AnalysisStatus.PENDING,
    )


def test_api_death_between_reservation_and_enqueue_is_recovered(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    queue = FakeQueue()
    install_queue(monkeypatch, queue)
    stable_id = jobs_service._analysis_job_id(row.id)

    # Before: the SQL row records work that was never dispatched.
    assert operations.get_analysis_result(row.id).job_id is None

    summary = jobs_service.reconcile_analysis_results(batch_size=5)

    recovered = operations.get_analysis_result(row.id)
    assert recovered.status is constants.AnalysisStatus.PENDING
    assert recovered.job_id == stable_id
    assert recovered.dispatch_count == 1
    assert queue.enqueued == [stable_id]
    assert summary["redispatched"] == 1


def test_enqueue_before_job_link_persistence_links_without_duplicate(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    stable_id = jobs_service._analysis_job_id(row.id)
    queue = FakeQueue()
    # The job reached Redis, then the API died before persisting job_id.
    queue.jobs[stable_id] = FakeJob(stable_id, "queued")
    install_queue(monkeypatch, queue)

    summary = jobs_service.reconcile_analysis_results(batch_size=5)

    recovered = operations.get_analysis_result(row.id)
    assert recovered.job_id == stable_id
    assert queue.enqueued == []
    assert summary["linked"] == 1
    assert len(queue.jobs) == 1


def test_worker_interrupted_before_running_is_redispatched_safely(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    stable_id = jobs_service._analysis_job_id(row.id)
    queue = FakeQueue()
    # The worker died before start_analysis_attempt; its job is already failed.
    queue.jobs[stable_id] = FakeJob(stable_id, "failed")
    install_queue(monkeypatch, queue)

    summary = jobs_service.reconcile_analysis_results(batch_size=5)

    recovered = operations.get_analysis_result(row.id)
    assert recovered.status is constants.AnalysisStatus.PENDING
    assert recovered.attempt_count == 0
    assert recovered.dispatch_count == 1
    assert recovered.job_id == stable_id
    assert queue.enqueued == [stable_id]
    assert summary["redispatched"] == 1


def test_worker_interrupted_after_running_reaches_safe_terminal_state(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    install_queue(monkeypatch, FakeQueue())
    t0 = datetime.now(timezone.utc)

    running = operations.start_analysis_attempt(row.id, t0, lease_seconds=0)
    assert running.status is constants.AnalysisStatus.RUNNING
    assert running.execution_id

    # Before reconciliation the row stays RUNNING forever: no code path can
    # prove the provider call is dead.
    assert operations.get_analysis_result(row.id).status is constants.AnalysisStatus.RUNNING

    summary = jobs_service.reconcile_analysis_results(batch_size=5)

    recovered = operations.get_analysis_result(row.id)
    assert recovered.status is constants.AnalysisStatus.FAILED
    assert recovered.error_code == "provider_result_unknown"
    assert recovered.lease_expires_at is None
    assert summary["abandoned"] == 1


def test_completion_persistence_failure_is_reconciled(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    install_queue(monkeypatch, FakeQueue())
    t0 = datetime.now(timezone.utc)

    running = operations.start_analysis_attempt(row.id, t0, lease_seconds=0)
    output = DeterministicFakeAnalyzer().analyze(
        AnalysisInputSnapshot.model_validate_json(row.input_snapshot)
    )

    # The provider call returned, but persistence happens after the lease.
    stored = operations.complete_analysis_result(
        row.id,
        output.summary,
        t0 + timedelta(seconds=5),
        execution_id=running.execution_id,
    )
    assert stored is None
    assert operations.get_analysis_result(row.id).status is constants.AnalysisStatus.RUNNING

    jobs_service.reconcile_analysis_results(batch_size=5)

    recovered = operations.get_analysis_result(row.id)
    assert recovered.status is constants.AnalysisStatus.FAILED
    assert recovered.error_code == "provider_result_unknown"


def test_redis_outage_leaves_row_recoverable_then_redispatches(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    queue = FakeQueue(unavailable=True)
    install_queue(monkeypatch, queue)

    first = jobs_service.reconcile_analysis_results(batch_size=5)

    assert first["redis_unavailable"] == 1
    still_pending = operations.get_analysis_result(row.id)
    assert still_pending.status is constants.AnalysisStatus.PENDING
    assert still_pending.job_id is None

    queue.unavailable = False
    second = jobs_service.reconcile_analysis_results(batch_size=5)

    recovered = operations.get_analysis_result(row.id)
    assert recovered.job_id == jobs_service._analysis_job_id(row.id)
    assert second["redispatched"] == 1


def test_two_reconcilers_do_not_create_duplicate_active_execution(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    queue = FakeQueue()
    install_queue(monkeypatch, queue)
    stable_id = jobs_service._analysis_job_id(row.id)
    errors = []

    def run_reconciler():
        try:
            jobs_service.reconcile_analysis_results(batch_size=5)
        except Exception as exc:  # pragma: no cover - exposed on failure
            errors.append(exc)

    threads = [threading.Thread(target=run_reconciler) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert queue.enqueued.count(stable_id) == 1
    active = [
        job for job in queue.jobs.values()
        if job.status in jobs_service.ANALYSIS_ACTIVE_JOB_STATUSES
    ]
    assert len(active) == 1
    assert operations.get_analysis_result(row.id).job_id == stable_id


def test_obsolete_worker_completion_after_recovery_is_rejected(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    install_queue(monkeypatch, FakeQueue())
    t0 = datetime.now(timezone.utc)

    running = operations.start_analysis_attempt(row.id, t0, lease_seconds=0)
    jobs_service.reconcile_analysis_results(batch_size=5)
    assert operations.get_analysis_result(row.id).status is constants.AnalysisStatus.FAILED

    late = operations.complete_analysis_result(
        row.id,
        "late summary from a dead worker",
        t0 + timedelta(seconds=30),
        execution_id=running.execution_id,
    )

    assert late is None
    assert operations.get_analysis_result(row.id).status is constants.AnalysisStatus.FAILED


def test_completion_from_obsolete_execution_is_rejected(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    install_queue(monkeypatch, FakeQueue())
    t0 = datetime.now(timezone.utc)

    first = operations.start_analysis_attempt(row.id, t0, lease_seconds=60)
    assert operations.return_analysis_to_pending(
        row.id,
        t0 + timedelta(seconds=1),
        execution_id=first.execution_id,
    ) is not None
    second = operations.start_analysis_attempt(
        row.id,
        t0 + timedelta(seconds=2),
        lease_seconds=60,
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


def test_stale_reconciler_does_not_fail_newer_attempt(recovery_engine, monkeypatch):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    install_queue(monkeypatch, FakeQueue())
    t0 = datetime.now(timezone.utc)

    # Attempt A starts and its lease expires; a reconciler reads this snapshot.
    first = operations.start_analysis_attempt(row.id, t0, lease_seconds=0)
    stale_snapshot = operations.get_analysis_result(row.id)
    assert stale_snapshot.execution_id == first.execution_id

    # Recovery returns A to PENDING; a new live attempt B takes over.
    assert operations.return_analysis_to_pending(
        row.id,
        t0 + timedelta(seconds=1),
        execution_id=first.execution_id,
    ) is not None
    second = operations.start_analysis_attempt(
        row.id, t0 + timedelta(seconds=2), lease_seconds=600
    )
    assert second.execution_id != first.execution_id

    # The stale reconciler acts on its earlier snapshot: zero rows match.
    outcome = jobs_service._reconcile_abandoned_analysis(
        stale_snapshot, t0 + timedelta(seconds=3)
    )
    assert outcome == "skipped"
    stored = operations.get_analysis_result(row.id)
    assert stored.status is constants.AnalysisStatus.RUNNING
    assert stored.execution_id == second.execution_id

    # The newer attempt can still complete normally.
    assert operations.complete_analysis_result(
        row.id,
        "fresh result",
        t0 + timedelta(seconds=4),
        execution_id=second.execution_id,
    ) is not None


def test_scheduled_retry_and_live_slow_attempt_are_not_abandoned(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine, ticket_id="ticket-1")
    add_ticket(recovery_engine, ticket_id="ticket-2")
    scheduled = operations.create_analysis_result(
        pending_result(result_id="result-scheduled", ticket_id="ticket-1")
    )
    slow = operations.create_analysis_result(
        pending_result(result_id="result-slow", ticket_id="ticket-2")
    )
    queue = FakeQueue()
    scheduled_id = jobs_service._analysis_job_id(scheduled.id)
    queue.jobs[scheduled_id] = FakeJob(scheduled_id, "scheduled")
    install_queue(monkeypatch, queue)
    t0 = datetime.now(timezone.utc)
    operations.attach_analysis_job(scheduled.id, scheduled_id, t0)
    operations.start_analysis_attempt(slow.id, t0, lease_seconds=600)

    summary = jobs_service.reconcile_analysis_results(batch_size=5)

    assert operations.get_analysis_result(scheduled.id).status is constants.AnalysisStatus.PENDING
    assert operations.get_analysis_result(slow.id).status is constants.AnalysisStatus.RUNNING
    assert queue.enqueued == []
    # The live slow attempt is not even selected because its lease is valid.
    assert summary["abandoned"] == 0
    assert summary["left_live"] == 1


def test_reconciliation_progresses_past_a_live_first_batch(
    recovery_engine,
    monkeypatch,
):
    """A live first page must not starve later recoverable PENDING rows.

    Three older PENDING rows keep live scheduled jobs; a later PENDING row has
    no job. Repeated bounded passes (batch size three) must reach and re-dispatch
    the later row within the documented ``ceil(W / B)`` bound.
    """
    for index in range(4):
        add_ticket(recovery_engine, ticket_id=f"ticket-{index}")
    base = datetime.now(timezone.utc)
    rows = [
        operations.create_analysis_result(
            pending_result(
                result_id=f"result-{index}",
                ticket_id=f"ticket-{index}",
                now=base + timedelta(seconds=index),
            )
        )
        for index in range(4)
    ]
    queue = FakeQueue()
    for row in rows[:3]:
        stable = jobs_service._analysis_job_id(row.id)
        queue.jobs[stable] = FakeJob(stable, "scheduled")
        operations.attach_analysis_job(row.id, stable, base)
    install_queue(monkeypatch, queue)

    reached = False
    for _ in range(5):
        jobs_service.reconcile_analysis_results(batch_size=3)
        if operations.get_analysis_result(rows[3].id).job_id is not None:
            reached = True
            break

    assert reached, "later recoverable row was never reached by bounded passes"
    recovered = operations.get_analysis_result(rows[3].id)
    assert recovered.status is constants.AnalysisStatus.PENDING
    assert recovered.job_id == jobs_service._analysis_job_id(rows[3].id)
    assert recovered.dispatch_count == 1
    # Only the starved row was dispatched; the live first-batch jobs are intact.
    assert queue.enqueued == [jobs_service._analysis_job_id(rows[3].id)]
    for row in rows[:3]:
        stored = operations.get_analysis_result(row.id)
        assert stored.job_id == jobs_service._analysis_job_id(row.id)
        assert stored.dispatch_count == 0
        assert stored.reconciliation_attempted_at is not None


def test_terminal_rows_are_not_rerun_when_job_result_expired(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result())
    queue = FakeQueue()
    install_queue(monkeypatch, queue)
    t0 = datetime.now(timezone.utc)
    running = operations.start_analysis_attempt(row.id, t0, lease_seconds=60)
    operations.complete_analysis_result(
        row.id,
        "Payment failed: Card payment returns error 500",
        t0 + timedelta(seconds=1),
        execution_id=running.execution_id,
    )
    # The RQ result has expired and the job is gone from Redis.
    queue.jobs.clear()

    summary = jobs_service.reconcile_analysis_results(batch_size=5)

    assert operations.get_analysis_result(row.id).status is constants.AnalysisStatus.COMPLETED
    assert queue.enqueued == []
    assert summary["considered"] == 0


def test_recovery_preserves_provider_provenance_and_input_snapshot(
    recovery_engine,
    monkeypatch,
):
    add_ticket(recovery_engine)
    row = operations.create_analysis_result(pending_result(
        provider="openrouter",
        model="openai/gpt-oss-20b",
        prompt_version="ticket_summary_v1",
    ))
    original_snapshot = operations.get_analysis_result(row.id).input_snapshot
    install_queue(monkeypatch, FakeQueue())

    jobs_service.reconcile_analysis_results(batch_size=5)

    recovered = operations.get_analysis_result(row.id)
    assert recovered.provider == "openrouter"
    assert recovered.model == "openai/gpt-oss-20b"
    assert recovered.prompt_version == "ticket_summary_v1"
    assert recovered.input_snapshot == original_snapshot


def test_analysis_reconciliation_schedule_is_bounded_and_registered():
    schedule = jobs_cron.ANALYSIS_RECONCILIATION_SCHEDULE

    assert schedule["func"] is jobs_service.reconcile_analysis_results
    assert schedule["queue_name"] == "ticket_jobs"
    assert schedule["interval"] > 0
    assert schedule["kwargs"]["batch_size"] > 0


def test_abandoned_recovery_runs_on_configured_engine(mutation_engine, monkeypatch):
    install_queue(monkeypatch, FakeQueue())
    row = operations.create_analysis_result(pending_result(ticket_id=None, requester_id=None))
    t0 = datetime.now(timezone.utc)
    running = operations.start_analysis_attempt(row.id, t0, lease_seconds=0)
    assert running is not None

    jobs_service.reconcile_analysis_results(batch_size=5)

    recovered = operations.get_analysis_result(row.id)
    assert recovered.status is constants.AnalysisStatus.FAILED
    assert recovered.error_code == "provider_result_unknown"


def test_owner_guard_runs_on_configured_engine(mutation_engine, monkeypatch):
    install_queue(monkeypatch, FakeQueue())
    row = operations.create_analysis_result(pending_result(ticket_id=None, requester_id=None))
    t0 = datetime.now(timezone.utc)
    first = operations.start_analysis_attempt(row.id, t0, lease_seconds=60)
    assert operations.return_analysis_to_pending(
        row.id,
        t0 + timedelta(seconds=1),
        execution_id=first.execution_id,
    ) is not None
    second = operations.start_analysis_attempt(
        row.id,
        t0 + timedelta(seconds=2),
        lease_seconds=60,
    )

    assert operations.complete_analysis_result(
        row.id,
        "obsolete",
        t0 + timedelta(seconds=3),
        execution_id=first.execution_id,
    ) is None
    assert operations.complete_analysis_result(
        row.id,
        "current",
        t0 + timedelta(seconds=3),
        execution_id=second.execution_id,
    ) is not None


def test_sqlite_migration_adds_execution_ownership_and_expires_running(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'phase-e.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE analysis_result (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                input_snapshot TEXT NOT NULL,
                summary VARCHAR(300),
                error_code VARCHAR(50),
                error_message VARCHAR(255),
                ticket_id VARCHAR(36),
                job_id VARCHAR(100),
                requester_id VARCHAR(36),
                provider VARCHAR(30),
                model VARCHAR(100),
                prompt_version VARCHAR(50),
                input_tokens INTEGER,
                output_tokens INTEGER,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                completed_at DATETIME,
                updated_at DATETIME NOT NULL,
                status VARCHAR(9) NOT NULL
            )
            """
        ))
        connection.execute(text(
            """
            INSERT INTO analysis_result (
                id, input_snapshot, ticket_id, attempt_count, created_at,
                started_at, updated_at, status
            ) VALUES (
                'legacy-running', '{}', NULL, 1, '2026-07-23 01:00:00',
                '2026-07-23 01:00:01', '2026-07-23 01:00:01', 'RUNNING'
            )
            """
        ))

    migrate_analysis_result_contract(engine)
    migrate_analysis_result_contract(engine)

    columns = {
        column["name"]: column for column in
        inspect(engine).get_columns("analysis_result")
    }
    assert "execution_id" in columns
    assert "lease_expires_at" in columns
    assert "dispatch_count" in columns
    assert "reconciliation_attempted_at" in columns
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT lease_expires_at, dispatch_count, status "
            "FROM analysis_result WHERE id = 'legacy-running'"
        )).one()
    assert row.status == "RUNNING"
    assert row.lease_expires_at is not None
    assert row.dispatch_count == 0
    engine.dispose()


def test_sqlite_upgrade_with_existing_data_preserves_rows_and_adds_marker(
    tmp_path,
):
    """A populated pre-fairness SQLite database upgrades without data loss."""
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'upgrade-with-data.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE analysis_result (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                input_snapshot TEXT NOT NULL,
                summary VARCHAR(300),
                error_code VARCHAR(50),
                error_message VARCHAR(255),
                ticket_id VARCHAR(36),
                job_id VARCHAR(100),
                requester_id VARCHAR(36),
                provider VARCHAR(30),
                model VARCHAR(100),
                prompt_version VARCHAR(50),
                input_tokens INTEGER,
                output_tokens INTEGER,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                dispatch_count INTEGER NOT NULL DEFAULT 0,
                execution_id VARCHAR(36),
                lease_expires_at DATETIME,
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                completed_at DATETIME,
                updated_at DATETIME NOT NULL,
                status VARCHAR(9) NOT NULL
            )
            """
        ))
        connection.execute(text(
            """
            INSERT INTO analysis_result (
                id, input_snapshot, ticket_id, provider, model, prompt_version,
                attempt_count, created_at, started_at, completed_at, updated_at,
                status, summary, error_code, error_message
            ) VALUES
                ('keep-pending', '{}', NULL, 'fake', 'deterministic-fake-v1',
                 'ticket_summary_v1', 0, '2026-07-23 01:00:00', NULL, NULL,
                 '2026-07-23 01:00:00', 'PENDING', NULL, NULL, NULL),
                ('keep-running', '{}', NULL, 'fake', 'deterministic-fake-v1',
                 'ticket_summary_v1', 1, '2026-07-23 01:00:00',
                 '2026-07-23 01:00:01', NULL, '2026-07-23 01:00:01', 'RUNNING',
                 NULL, NULL, NULL),
                ('keep-completed', '{}', NULL, 'fake', 'deterministic-fake-v1',
                 'ticket_summary_v1', 1, '2026-07-23 01:00:00',
                 '2026-07-23 01:00:01', '2026-07-23 01:00:02',
                 '2026-07-23 01:00:02', 'COMPLETED', 'Already summarized', NULL,
                 NULL),
                ('keep-failed', '{}', NULL, 'fake', 'deterministic-fake-v1',
                 'ticket_summary_v1', 1, '2026-07-23 01:00:00', NULL,
                 '2026-07-23 01:00:02', '2026-07-23 01:00:02', 'FAILED', NULL,
                 'provider_result_unknown', 'interrupted')
            """
        ))

    migrate_analysis_result_contract(engine)
    migrate_analysis_result_contract(engine)  # idempotent

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("analysis_result")
    }
    assert "reconciliation_attempted_at" in columns
    with engine.connect() as connection:
        rows = {
            row.id: row
            for row in connection.execute(text(
                "SELECT id, status, summary, error_code, "
                "reconciliation_attempted_at FROM analysis_result"
            ))
        }
    assert set(rows) == {
        "keep-pending",
        "keep-running",
        "keep-completed",
        "keep-failed",
    }
    assert rows["keep-completed"].summary == "Already summarized"
    assert rows["keep-failed"].error_code == "provider_result_unknown"
    # Terminal rows keep their state and are not resurrected by the migration.
    assert rows["keep-completed"].status == "COMPLETED"
    assert rows["keep-failed"].status == "FAILED"
    # Existing rows start as never-considered so they are scanned first.
    assert all(row.reconciliation_attempted_at is None for row in rows.values())
    engine.dispose()
