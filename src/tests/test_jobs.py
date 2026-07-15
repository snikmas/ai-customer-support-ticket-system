from types import SimpleNamespace
import subprocess
import sys

import pytest

from src import constants
from src.jobs import service as jobs_service
from src.jobs import tasks as job_tasks
from src.exceptions import AuthorizationError, TicketNotFoundError
from src.models import JobResponse
from src.services import tickets as ticket_service


@pytest.mark.parametrize(
    ("rq_status", "expected"),
    [
        ("queued", constants.JobStatus.QUEUED),
        ("started", constants.JobStatus.RUNNING),
        ("finished", constants.JobStatus.COMPLETED),
        ("failed", constants.JobStatus.FAILED),
        ("deferred", constants.JobStatus.DEFERRED),
        ("scheduled", constants.JobStatus.SCHEDULED),
        ("stopped", constants.JobStatus.STOPPED),
        ("canceled", constants.JobStatus.CANCELED),
        ("rate_limited", constants.JobStatus.RATE_LIMITED),
        ("ready_to_enqueue", constants.JobStatus.READY_TO_ENQUEUE),
        ("future_rq_status", constants.JobStatus.UNKNOWN),
    ],
)
def test_translate_rq_status_preserves_non_failure_states(rq_status, expected):
    assert constants.translate_rq_status(rq_status) is expected


def test_get_job_includes_result_only_after_success(monkeypatch, make_user):
    result = {"ticket_id": "ticket-1", "priority": 2}
    job = SimpleNamespace(
        id="job-1",
        args=("ticket-1",),
        result=result,
        get_status=lambda: "finished",
    )
    queue = SimpleNamespace(fetch_job=lambda job_id: job if job_id == job.id else None)
    monkeypatch.setattr(jobs_service, "get_ticket_jobs_queue", lambda: queue)
    monkeypatch.setattr(jobs_service, "_get_ticket_for_requester", lambda *_: object())

    response = jobs_service.get_job(job.id, make_user(role=constants.Role.AGENT))

    assert response.result == result


def test_get_job_hides_result_while_job_is_not_finished(monkeypatch, make_user):
    job = SimpleNamespace(
        id="job-1",
        args=("ticket-1",),
        result={"partial": "must not leak"},
        get_status=lambda: "started",
    )
    queue = SimpleNamespace(fetch_job=lambda _: job)
    monkeypatch.setattr(jobs_service, "get_ticket_jobs_queue", lambda: queue)
    monkeypatch.setattr(jobs_service, "_get_ticket_for_requester", lambda *_: object())

    response = jobs_service.get_job(job.id, make_user(role=constants.Role.AGENT))

    assert response.result is None


def test_start_job_uses_bounded_rq_settings_and_logs(monkeypatch, caplog):
    captured = {}

    class FakeJob:
        id = "job-1"

        def get_status(self):
            return "queued"

    class FakeQueue:
        def enqueue(self, function, ticket_id, **settings):
            captured.update(
                function=function,
                ticket_id=ticket_id,
                settings=settings,
            )
            return FakeJob()

    monkeypatch.setattr(jobs_service, "get_ticket_jobs_queue", lambda: FakeQueue())
    caplog.set_level("INFO")

    response = jobs_service.start_ticket_inspection_job("ticket-1")

    assert captured == {
        "function": job_tasks.inspect_ticket,
        "ticket_id": "ticket-1",
        "settings": {"job_timeout": 180, "result_ttl": 600},
    }
    assert response.job_id == "job-1"
    assert response.status is constants.JobStatus.QUEUED
    assert "Ticket inspection job enqueued" in caplog.text


def test_get_job_rejects_non_agent_before_reading_redis(monkeypatch, make_user):
    monkeypatch.setattr(
        jobs_service,
        "get_ticket_jobs_queue",
        lambda: pytest.fail("unauthorized users must be rejected before Redis access"),
    )

    with pytest.raises(AuthorizationError):
        jobs_service.get_job("job-1", make_user(role=constants.Role.USER))


def test_job_creation_rejects_customer_before_cache_or_redis(monkeypatch, make_user):
    monkeypatch.setattr(
        ticket_service,
        "check_cached_ticket",
        lambda _: pytest.fail("unauthorized users must be rejected before cache access"),
    )

    with pytest.raises(AuthorizationError):
        ticket_service.analysis_job(
            "ticket-1",
            make_user(role=constants.Role.USER),
        )


def test_assigned_agent_can_create_inspection_job(
    monkeypatch,
    make_user,
    make_ticket,
):
    agent = make_user(id="agent-1", role=constants.Role.AGENT)
    ticket = make_ticket(assigned_agent_id=agent.id)
    expected = JobResponse(job_id="job-1", status=constants.JobStatus.QUEUED)
    monkeypatch.setattr(ticket_service, "check_cached_ticket", lambda _: ticket)
    monkeypatch.setattr(
        ticket_service,
        "start_ticket_inspection_job",
        lambda ticket_id: expected,
    )

    assert ticket_service.analysis_job(ticket.id, agent) == expected


def test_agent_cannot_create_job_for_another_agents_ticket(
    monkeypatch,
    make_user,
    make_ticket,
):
    agent = make_user(id="agent-1", role=constants.Role.AGENT)
    ticket = make_ticket(assigned_agent_id="agent-2")
    monkeypatch.setattr(ticket_service, "check_cached_ticket", lambda _: ticket)
    monkeypatch.setattr(
        ticket_service,
        "start_ticket_inspection_job",
        lambda _: pytest.fail("unauthorized jobs must not reach Redis"),
    )

    with pytest.raises(AuthorizationError):
        ticket_service.analysis_job(ticket.id, agent)


def test_inspect_ticket_returns_safe_deterministic_result(monkeypatch, make_ticket, caplog):
    ticket = make_ticket(
        status=constants.Status.IN_PROGRESS,
        priority=constants.Priority.HIGH,
    )
    monkeypatch.setattr(job_tasks, "get_ticket", lambda ticket_id: ticket)
    caplog.set_level("INFO")

    result = job_tasks.inspect_ticket(ticket.id)

    assert result == {
        "ticket_id": ticket.id,
        "status": constants.Status.IN_PROGRESS.value,
        "priority": constants.Priority.HIGH.value,
        "deleted": False,
    }
    assert "Ticket inspection started" in caplog.text
    assert "Ticket inspection completed" in caplog.text


def test_inspect_ticket_logs_missing_ticket_without_ticket_contents(monkeypatch, caplog):
    monkeypatch.setattr(job_tasks, "get_ticket", lambda ticket_id: None)
    caplog.set_level("WARNING")

    with pytest.raises(TicketNotFoundError):
        job_tasks.inspect_ticket("missing-ticket")

    assert "Ticket inspection failed because the ticket was not found" in caplog.text


def test_worker_task_imports_in_a_fresh_process():
    completed = subprocess.run(
        [sys.executable, "-c", "from src.jobs.tasks import inspect_ticket"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
