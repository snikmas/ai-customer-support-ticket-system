from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from main import app
from src import constants
from src.analyzers import (
    AnalysisInputSnapshot,
    AnalysisOutput,
    PermanentAnalysisError,
    RetryableAnalysisError,
)
from src.db import operations
from src.db.models import Base, Comment, Ticket
from src.core import config
from src.dependencies.auth import get_current_user
from src.exceptions import (
    AnalysisEnqueueUnavailableError,
    AnalysisRateLimitUnavailableError,
    AuthorizationError,
)
from src.jobs import service as jobs_service
from src.jobs import tasks as job_tasks
from src.services import analysis_results


@pytest.fixture
def lifecycle_engine(tmp_path, monkeypatch):
    test_engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'analysis-lifecycle.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(operations, "engine", test_engine)
    yield test_engine
    test_engine.dispose()


def add_ticket(
    engine,
    *,
    ticket_id="ticket-1",
    assigned_agent_id="agent-1",
    deleted_at=None,
):
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id=ticket_id,
        title="Payment failed",
        description="Card payment returns error 500",
        category=constants.Category.BILLING,
        tags=constants.serialize_tags([constants.Tag.ERROR_500]),
        department_id=None,
        assigned_agent_id=assigned_agent_id,
        creator_user_id="customer-1",
        status=constants.Status.IN_PROGRESS,
        priority=constants.Priority.HIGH,
        updated_at=now,
        created_at=now,
        due_at=None,
        deleted_at=deleted_at,
    )
    with Session(engine) as session:
        session.add(ticket)
        session.commit()
    return ticket


def configure_successful_request(monkeypatch):
    allowance_calls = []
    enqueue_calls = []

    monkeypatch.setattr(
        analysis_results,
        "consume_analysis_creation_allowance",
        lambda user_id: allowance_calls.append(user_id),
    )

    def enqueue(result_id):
        enqueue_calls.append(result_id)
        return SimpleNamespace(id=f"job-{len(enqueue_calls)}")

    monkeypatch.setattr(jobs_service, "enqueue_analysis_result_job", enqueue)
    return allowance_calls, enqueue_calls


def test_assigned_agent_creates_durable_pending_result(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    add_ticket(lifecycle_engine)
    allowance_calls, enqueue_calls = configure_successful_request(monkeypatch)
    agent = make_user(id="agent-1", role=constants.Role.AGENT)

    result = analysis_results.request_analysis("ticket-1", agent)

    assert result.status is constants.AnalysisStatus.PENDING
    assert result.job_id == "job-1"
    assert result.attempt_count == 0
    assert allowance_calls == ["agent-1"]
    assert enqueue_calls == [result.id]


def test_request_freezes_only_bounded_latest_public_comments(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    add_ticket(lifecycle_engine)
    now = datetime.now(timezone.utc)
    public_bodies = []
    with Session(lifecycle_engine) as session:
        for index in range(12):
            prefix = f"public-{index}-"
            body = prefix + ("x" * (1000 - len(prefix)))
            public_bodies.append(body)
            session.add(Comment(
                id=f"public-{index}",
                ticket_id="ticket-1",
                author_user_id="customer-1",
                body=body,
                visibility=constants.Visibility.PUBLIC,
                edited_at=None,
                created_at=now + timedelta(seconds=index),
                updated_at=now + timedelta(seconds=index),
                deleted_at=None,
                deleted_by_user_id=None,
                parent_comment_id=None,
                attachments_count=9,
                source=constants.Source.WEB,
            ))
        session.add_all([
            Comment(
                id="internal-secret",
                ticket_id="ticket-1",
                author_user_id="agent-1",
                body="INTERNAL_SECRET",
                visibility=constants.Visibility.INTERNAL,
                edited_at=None,
                created_at=now + timedelta(seconds=20),
                updated_at=now + timedelta(seconds=20),
                deleted_at=None,
                deleted_by_user_id=None,
                parent_comment_id=None,
                attachments_count=0,
                source=constants.Source.WEB,
            ),
            Comment(
                id="deleted-secret",
                ticket_id="ticket-1",
                author_user_id="customer-1",
                body="DELETED_SECRET",
                visibility=constants.Visibility.PUBLIC,
                edited_at=None,
                created_at=now + timedelta(seconds=21),
                updated_at=now + timedelta(seconds=21),
                deleted_at=now + timedelta(seconds=22),
                deleted_by_user_id="agent-1",
                parent_comment_id=None,
                attachments_count=0,
                source=constants.Source.WEB,
            ),
        ])
        session.commit()
    configure_successful_request(monkeypatch)

    pending = analysis_results.request_analysis(
        "ticket-1",
        make_user(id="agent-1", role=constants.Role.AGENT),
    )
    frozen_json = operations.get_analysis_result(pending.id).input_snapshot
    snapshot = AnalysisInputSnapshot.model_validate_json(frozen_json)

    assert snapshot.public_comments == tuple(public_bodies[4:12])
    assert sum(map(len, snapshot.public_comments)) == 8_000
    assert "INTERNAL_SECRET" not in frozen_json
    assert "DELETED_SECRET" not in frozen_json
    assert "attachments_count" not in frozen_json

    with Session(lifecycle_engine) as session:
        session.get(Comment, "public-11").body = "changed after request"
        session.commit()
    assert (
        AnalysisInputSnapshot.model_validate_json(
            operations.get_analysis_result(pending.id).input_snapshot
        ).public_comments
        == snapshot.public_comments
    )


def test_sequential_duplicate_reuses_result_without_rate_limit_or_enqueue(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    add_ticket(lifecycle_engine)
    allowance_calls, enqueue_calls = configure_successful_request(monkeypatch)
    agent = make_user(id="agent-1", role=constants.Role.AGENT)

    first = analysis_results.request_analysis("ticket-1", agent)
    second = analysis_results.request_analysis("ticket-1", agent)

    assert second.id == first.id
    assert allowance_calls == ["agent-1"]
    assert len(enqueue_calls) == 1


def test_concurrent_duplicate_requests_create_and_charge_once(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    add_ticket(lifecycle_engine)
    allowance_calls, enqueue_calls = configure_successful_request(monkeypatch)
    agent = make_user(id="agent-1", role=constants.Role.AGENT)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda _: analysis_results.request_analysis("ticket-1", agent),
            range(2),
        ))

    assert len({result.id for result in results}) == 1
    assert allowance_calls == ["agent-1"]
    assert len(enqueue_calls) == 1


@pytest.mark.parametrize(
    "role",
    [
        constants.Role.USER,
        constants.Role.AGENT_READONLY,
        constants.Role.BOT,
        constants.Role.API,
    ],
)
def test_unauthorized_roles_cannot_request_analysis(
    lifecycle_engine,
    monkeypatch,
    make_user,
    role,
):
    add_ticket(lifecycle_engine)
    monkeypatch.setattr(
        analysis_results,
        "consume_analysis_creation_allowance",
        lambda _: pytest.fail("unauthorized requests must not consume Redis allowance"),
    )

    with pytest.raises(AuthorizationError):
        analysis_results.request_analysis(
            "ticket-1",
            make_user(id="user-1", role=role),
        )


def test_agent_cannot_analyze_another_agents_ticket(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    add_ticket(lifecycle_engine, assigned_agent_id="agent-2")
    monkeypatch.setattr(
        analysis_results,
        "consume_analysis_creation_allowance",
        lambda _: pytest.fail("unauthorized requests must not reach Redis"),
    )

    with pytest.raises(AuthorizationError):
        analysis_results.request_analysis(
            "ticket-1",
            make_user(id="agent-1", role=constants.Role.AGENT),
        )


@pytest.mark.parametrize("role", [constants.Role.MANAGER, constants.Role.ADMIN])
def test_manager_and_admin_are_not_rate_limit_exempt(
    lifecycle_engine,
    monkeypatch,
    make_user,
    role,
):
    add_ticket(lifecycle_engine)
    allowance_calls, _ = configure_successful_request(monkeypatch)

    analysis_results.request_analysis(
        "ticket-1",
        make_user(id="manager-1", role=role),
    )

    assert allowance_calls == ["manager-1"]


def test_redis_outage_creates_no_result(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    add_ticket(lifecycle_engine)
    monkeypatch.setattr(
        analysis_results,
        "consume_analysis_creation_allowance",
        lambda _: (_ for _ in ()).throw(AnalysisRateLimitUnavailableError()),
    )

    with pytest.raises(AnalysisRateLimitUnavailableError):
        analysis_results.request_analysis(
            "ticket-1",
            make_user(id="agent-1", role=constants.Role.AGENT),
        )

    assert operations.get_analysis_results_by_ticket("ticket-1") == []


def test_enqueue_failure_is_visible_as_failed_result(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    add_ticket(lifecycle_engine)
    monkeypatch.setattr(
        analysis_results,
        "consume_analysis_creation_allowance",
        lambda _: None,
    )
    monkeypatch.setattr(
        jobs_service,
        "enqueue_analysis_result_job",
        lambda _: (_ for _ in ()).throw(ConnectionError("redis secret")),
    )

    with pytest.raises(AnalysisEnqueueUnavailableError):
        analysis_results.request_analysis(
            "ticket-1",
            make_user(id="agent-1", role=constants.Role.AGENT),
        )

    [failed] = operations.get_analysis_results_by_ticket("ticket-1")
    assert failed.status is constants.AnalysisStatus.FAILED
    assert failed.error_code == "enqueue_failed"
    assert failed.error_message == "Analysis could not be queued"


def create_pending_for_worker(engine, monkeypatch, make_user):
    add_ticket(engine)
    configure_successful_request(monkeypatch)
    return analysis_results.request_analysis(
        "ticket-1",
        make_user(id="agent-1", role=constants.Role.AGENT),
    )


def test_worker_completes_same_sql_result(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    pending = create_pending_for_worker(lifecycle_engine, monkeypatch, make_user)

    job_result = job_tasks.analyze_analysis_result(pending.id)
    completed = operations.get_analysis_result(pending.id)

    assert job_result == {
        "analysis_result_id": pending.id,
        "status": "completed",
    }
    assert completed.status is constants.AnalysisStatus.COMPLETED
    assert completed.attempt_count == 1
    assert completed.summary == (
        "Payment failed: Card payment returns error 500"
    )
    assert completed.provider == "fake"
    assert completed.model == "deterministic-fake-v1"
    assert completed.prompt_version == "ticket_summary_v1"
    assert completed.input_tokens is None
    assert completed.output_tokens is None


def test_worker_persists_successful_provider_tokens(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    pending = create_pending_for_worker(lifecycle_engine, monkeypatch, make_user)

    class TokenAnalyzer:
        def analyze(self, snapshot):
            return AnalysisOutput(
                summary="Payment fails. The card returns an error.",
                input_tokens=41,
                output_tokens=9,
            )

    monkeypatch.setattr(job_tasks, "build_analyzer", lambda **_: TokenAnalyzer())

    job_tasks.analyze_analysis_result(pending.id)
    completed = operations.get_analysis_result(pending.id)

    assert completed.status is constants.AnalysisStatus.COMPLETED
    assert completed.summary == "Payment fails. The card returns an error."
    assert completed.input_tokens == 41
    assert completed.output_tokens == 9


def test_retryable_failure_returns_to_pending_then_fails_after_third_attempt(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    pending = create_pending_for_worker(lifecycle_engine, monkeypatch, make_user)

    class RetryableAnalyzer:
        def analyze(self, snapshot):
            raise RetryableAnalysisError("provider secret must not persist")

    current_job = SimpleNamespace(retries_left=2, save=lambda: None)
    monkeypatch.setattr(job_tasks, "build_analyzer", lambda **_: RetryableAnalyzer())
    monkeypatch.setattr(job_tasks, "get_current_job", lambda: current_job)

    for expected_attempt in (1, 2):
        with pytest.raises(RetryableAnalysisError):
            job_tasks.analyze_analysis_result(pending.id)
        waiting = operations.get_analysis_result(pending.id)
        assert waiting.status is constants.AnalysisStatus.PENDING
        assert waiting.attempt_count == expected_attempt

    with pytest.raises(RetryableAnalysisError):
        job_tasks.analyze_analysis_result(pending.id)

    failed = operations.get_analysis_result(pending.id)
    assert failed.status is constants.AnalysisStatus.FAILED
    assert failed.attempt_count == 3
    assert failed.error_code == "provider_unavailable"
    assert "secret" not in failed.error_message
    assert current_job.retries_left == 0


def test_deleted_ticket_is_permanent_failure_without_retry(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    pending = create_pending_for_worker(lifecycle_engine, monkeypatch, make_user)
    with Session(lifecycle_engine) as session:
        ticket = session.get(Ticket, "ticket-1")
        ticket.deleted_at = datetime.now(timezone.utc)
        session.commit()

    current_job = SimpleNamespace(retries_left=2, save=lambda: None)
    monkeypatch.setattr(job_tasks, "get_current_job", lambda: current_job)

    with pytest.raises(PermanentAnalysisError):
        job_tasks.analyze_analysis_result(pending.id)

    failed = operations.get_analysis_result(pending.id)
    assert failed.status is constants.AnalysisStatus.FAILED
    assert failed.error_code == "ticket_deleted"
    assert failed.attempt_count == 1
    assert current_job.retries_left == 0


def test_permanent_provider_failure_keeps_safe_category_without_retry(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    pending = create_pending_for_worker(lifecycle_engine, monkeypatch, make_user)

    class AuthFailureAnalyzer:
        def analyze(self, snapshot):
            raise PermanentAnalysisError(
                "raw provider response with secret",
                code="provider_auth_failed",
                safe_message="OpenRouter authentication failed",
            )

    current_job = SimpleNamespace(retries_left=2, save=lambda: None)
    monkeypatch.setattr(job_tasks, "build_analyzer", lambda **_: AuthFailureAnalyzer())
    monkeypatch.setattr(job_tasks, "get_current_job", lambda: current_job)

    with pytest.raises(PermanentAnalysisError):
        job_tasks.analyze_analysis_result(pending.id)

    failed = operations.get_analysis_result(pending.id)
    assert failed.status is constants.AnalysisStatus.FAILED
    assert failed.error_code == "provider_auth_failed"
    assert failed.error_message == "OpenRouter authentication failed"
    assert "secret" not in failed.error_message
    assert failed.input_tokens is None
    assert failed.output_tokens is None
    assert current_job.retries_left == 0


def test_missing_openrouter_configuration_fails_row_permanently(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    pending = create_pending_for_worker(lifecycle_engine, monkeypatch, make_user)
    with Session(lifecycle_engine) as session:
        session.execute(
            update(operations.AnalysisResult)
            .where(operations.AnalysisResult.id == pending.id)
            .values(provider="openrouter", model="openai/gpt-oss-20b")
        )
        session.commit()
    monkeypatch.setattr(config, "ANALYZER_PROVIDER", "openrouter")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(config, "OPENROUTER_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(config, "OPENROUTER_TIMEOUT_SECONDS", 20)
    current_job = SimpleNamespace(retries_left=2, save=lambda: None)
    monkeypatch.setattr(job_tasks, "get_current_job", lambda: current_job)

    with pytest.raises(PermanentAnalysisError):
        job_tasks.analyze_analysis_result(pending.id)

    failed = operations.get_analysis_result(pending.id)
    assert failed.status is constants.AnalysisStatus.FAILED
    assert failed.error_code == "provider_config_error"
    assert failed.error_message == "OpenRouter configuration is invalid"
    assert failed.attempt_count == 1
    assert current_job.retries_left == 0


def test_invalid_stored_snapshot_is_permanent_safe_failure(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    pending = create_pending_for_worker(lifecycle_engine, monkeypatch, make_user)
    with Session(lifecycle_engine) as session:
        session.execute(
            update(operations.AnalysisResult)
            .where(operations.AnalysisResult.id == pending.id)
            .values(input_snapshot='{"description":"missing required fields"}')
        )
        session.commit()

    current_job = SimpleNamespace(retries_left=2, save=lambda: None)
    monkeypatch.setattr(job_tasks, "get_current_job", lambda: current_job)

    with pytest.raises(PermanentAnalysisError):
        job_tasks.analyze_analysis_result(pending.id)

    failed = operations.get_analysis_result(pending.id)
    assert failed.status is constants.AnalysisStatus.FAILED
    assert failed.error_code == "invalid_analysis_snapshot"
    assert failed.error_message == "Stored analysis input is invalid"
    assert current_job.retries_left == 0


def test_original_requester_can_read_after_reassignment_but_not_history(
    lifecycle_engine,
    monkeypatch,
    make_user,
):
    pending = create_pending_for_worker(lifecycle_engine, monkeypatch, make_user)
    with Session(lifecycle_engine) as session:
        ticket = session.get(Ticket, "ticket-1")
        ticket.assigned_agent_id = "agent-2"
        session.commit()
    original_agent = make_user(id="agent-1", role=constants.Role.AGENT)

    assert analysis_results.get_analysis_result(pending.id, original_agent).id == pending.id
    with pytest.raises(AuthorizationError):
        analysis_results.get_ticket_analysis_results(
            "ticket-1",
            original_agent,
            limit=20,
            offset=0,
        )


def test_analysis_routes_are_registered_and_post_returns_202(monkeypatch, make_user):
    agent = make_user(id="agent-1", role=constants.Role.AGENT)
    result = SimpleNamespace(
        id="result-1",
        summary=None,
        error_code=None,
        error_message=None,
        ticket_id="ticket-1",
        job_id="job-1",
        provider="fake",
        model="deterministic-fake-v1",
        prompt_version="ticket_summary_v1",
        input_tokens=None,
        output_tokens=None,
        requester_id="agent-1",
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
        started_at=None,
        completed_at=None,
        updated_at=datetime.now(timezone.utc),
        status=constants.AnalysisStatus.PENDING,
    )
    app.dependency_overrides[get_current_user] = lambda: agent
    monkeypatch.setattr(analysis_results, "request_analysis", lambda *_: result)
    monkeypatch.setattr(analysis_results, "get_analysis_result", lambda *_: result)

    response = TestClient(app).post("/tickets/ticket-1/analysis-results")
    read_response = TestClient(app).get("/analysis-results/result-1")
    obsolete_response = TestClient(app).post("/tickets/ticket-1/analysis-jobs")

    assert response.status_code == 202
    assert response.json()["data"]["id"] == "result-1"
    assert read_response.status_code == 200
    assert read_response.json()["data"]["id"] == "result-1"
    assert obsolete_response.status_code == 404
