from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, delete, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src import constants
from src.analyzers import AnalysisInputSnapshot
from src.db import operations
from src.db.migrations import migrate_analysis_result_contract
from src.db.models import AnalysisResult as DbAnalysisResult
from src.db.models import Base, Ticket, User
from src.exceptions import AuthorizationError
from src.models import AnalysisResult as ApiAnalysisResult
from src.services import analysis_results


@pytest.fixture
def analysis_engine(tmp_path, monkeypatch):
    test_engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'analysis.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(operations, "engine", test_engine)
    yield test_engine
    test_engine.dispose()


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
        provider="fake",
        model="deterministic-fake-v1",
        prompt_version="ticket_summary_v1",
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


def test_analysis_result_api_model_matches_durable_contract():
    row = pending_result()

    response = ApiAnalysisResult.model_validate(row)

    assert response.summary is None
    assert response.error_code is None
    assert response.provider == "fake"
    assert response.model == "deterministic-fake-v1"
    assert response.prompt_version == "ticket_summary_v1"
    assert response.input_tokens is None
    assert response.output_tokens is None
    assert response.attempt_count == 0
    assert "input_snapshot" not in response.model_dump()
    assert "full_description" not in response.model_dump()


def test_database_allows_only_one_active_result_per_ticket(analysis_engine):
    operations.create_analysis_result(pending_result(result_id="result-1"))

    with pytest.raises(IntegrityError):
        operations.create_analysis_result(pending_result(result_id="result-2"))

    active = operations.get_active_analysis_result("ticket-1")
    assert active.id == "result-1"


def test_lifecycle_updates_same_row_and_preserves_first_start(analysis_engine):
    created_at = datetime(2026, 7, 23, 1, 0, tzinfo=timezone.utc)
    operations.create_analysis_result(pending_result(now=created_at))

    job_attached = operations.attach_analysis_job(
        "result-1",
        "rq-job-1",
        created_at + timedelta(seconds=1),
    )
    first_running = operations.start_analysis_attempt(
        "result-1",
        created_at + timedelta(seconds=2),
    )
    waiting = operations.return_analysis_to_pending(
        "result-1",
        created_at + timedelta(seconds=3),
    )
    second_running = operations.start_analysis_attempt(
        "result-1",
        created_at + timedelta(seconds=8),
    )
    completed = operations.complete_analysis_result(
        "result-1",
        "Payment failed: Card payment returns error 500",
        created_at + timedelta(seconds=9),
    )

    assert job_attached.job_id == "rq-job-1"
    assert first_running.attempt_count == 1
    assert waiting.status is constants.AnalysisStatus.PENDING
    assert second_running.attempt_count == 2
    assert second_running.started_at == first_running.started_at
    assert completed.status is constants.AnalysisStatus.COMPLETED
    assert completed.attempt_count == 2
    assert completed.completed_at == created_at + timedelta(seconds=9)
    assert operations.get_active_analysis_result("ticket-1") is None
    assert operations.get_analysis_result("result-1").summary.startswith("Payment")


def test_enqueue_failure_is_valid_without_worker_start(analysis_engine):
    now = datetime.now(timezone.utc)
    operations.create_analysis_result(pending_result(now=now))

    failed = operations.fail_analysis_result(
        "result-1",
        expected_statuses=(constants.AnalysisStatus.PENDING,),
        error_code="enqueue_failed",
        error_message="Analysis could not be queued",
        now=now + timedelta(seconds=1),
    )

    assert failed.status is constants.AnalysisStatus.FAILED
    assert failed.attempt_count == 0
    assert failed.started_at is None
    assert failed.completed_at is not None


def test_invalid_lifecycle_transition_is_a_no_op(analysis_engine):
    operations.create_analysis_result(pending_result())

    assert operations.complete_analysis_result(
        "result-1",
        "must not be stored",
        datetime.now(timezone.utc),
    ) is None
    assert operations.get_analysis_result("result-1").status is constants.AnalysisStatus.PENDING


def test_database_constraint_rejects_completed_result_without_summary(analysis_engine):
    invalid = pending_result()
    invalid.status = constants.AnalysisStatus.COMPLETED
    invalid.attempt_count = 1
    invalid.started_at = datetime.now(timezone.utc)
    invalid.completed_at = datetime.now(timezone.utc)

    with pytest.raises(IntegrityError):
        operations.create_analysis_result(invalid)


def test_analysis_contract_migration_is_idempotent_and_preserves_history(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy-analysis.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE analysis_result (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                summary VARCHAR(300) NOT NULL,
                full_description VARCHAR(2000) NOT NULL,
                ticket_id VARCHAR(36) NOT NULL,
                job_id VARCHAR(36) NOT NULL,
                requester_id VARCHAR(36) NOT NULL,
                created_at DATETIME NOT NULL,
                status VARCHAR(9) NOT NULL
            )
            """
        ))
        connection.execute(
            text(
                """
                INSERT INTO analysis_result (
                    id, summary, full_description, ticket_id, job_id,
                    requester_id, created_at, status
                ) VALUES (
                    'legacy-1', 'old summary', 'old details', 'ticket-1',
                    'job-1', 'user-1', '2026-07-23 01:00:00', 'COMPLETED'
                )
                """
            )
        )

    migrate_analysis_result_contract(engine)
    migrate_analysis_result_contract(engine)

    columns = {
        column["name"]: column for column in inspect(engine).get_columns("analysis_result")
    }
    assert "full_description" not in columns
    assert columns["summary"]["nullable"] is True
    assert columns["ticket_id"]["nullable"] is True
    assert columns["requester_id"]["nullable"] is True
    assert columns["provider"]["nullable"] is True
    assert columns["model"]["nullable"] is True
    assert columns["prompt_version"]["nullable"] is True
    assert columns["input_tokens"]["nullable"] is True
    assert columns["output_tokens"]["nullable"] is True
    with engine.connect() as connection:
        row = connection.execute(text(
            """
            SELECT status, summary, error_code, attempt_count
            FROM analysis_result WHERE id = 'legacy-1'
            """
        )).one()
    assert row == ("FAILED", None, "legacy_contract_migrated", 0)
    engine.dispose()


def test_analysis_migration_adds_nullable_provenance_to_stage5_table(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'stage5-analysis.db'}")
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
                attempt_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                completed_at DATETIME,
                updated_at DATETIME NOT NULL,
                status VARCHAR(9) NOT NULL
            )
            """
        ))

    migrate_analysis_result_contract(engine)
    migrate_analysis_result_contract(engine)

    columns = {
        column["name"]: column for column in inspect(engine).get_columns("analysis_result")
    }
    for column_name in (
        "provider",
        "model",
        "prompt_version",
        "input_tokens",
        "output_tokens",
    ):
        assert columns[column_name]["nullable"] is True
    engine.dispose()


def test_physical_ticket_and_requester_deletion_preserves_result(
    tmp_path,
    monkeypatch,
    make_user,
):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'analysis-delete.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    monkeypatch.setattr(operations, "engine", engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add_all([
            User(
                id="agent-1",
                nickname="agent-one",
                avatar_url=None,
                first_name="Agent",
                last_name="One",
                phone="+8613800000101",
                email="agent-one@example.com",
                role=constants.Role.AGENT,
                password="hash",
                updated_at=now,
                created_at=now,
                deleted_at=None,
                user_status=constants.UserStatus.ACTIVE,
            ),
            User(
                id="customer-1",
                nickname="customer-one",
                avatar_url=None,
                first_name="Customer",
                last_name="One",
                phone="+8613800000102",
                email="customer-one@example.com",
                role=constants.Role.USER,
                password="hash",
                updated_at=now,
                created_at=now,
                deleted_at=None,
                user_status=constants.UserStatus.ACTIVE,
            ),
        ])
        session.flush()
        session.add(Ticket(
            id="ticket-1",
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
        session.flush()
        session.add(pending_result(now=now))
        session.commit()

    with Session(engine) as session:
        session.execute(delete(Ticket).where(Ticket.id == "ticket-1"))
        session.execute(delete(User).where(User.id == "agent-1"))
        session.commit()

    preserved = operations.get_analysis_result("result-1")
    assert preserved.ticket_id is None
    assert preserved.requester_id is None

    manager = make_user(id="manager-1", role=constants.Role.MANAGER)
    ordinary_agent = make_user(id="agent-2", role=constants.Role.AGENT)
    assert analysis_results.get_analysis_result("result-1", manager).id == "result-1"
    with pytest.raises(AuthorizationError):
        analysis_results.get_analysis_result("result-1", ordinary_agent)
    engine.dispose()
