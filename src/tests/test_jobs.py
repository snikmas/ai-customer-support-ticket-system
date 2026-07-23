from types import SimpleNamespace
import subprocess
import sys

import pytest

from src import constants
from src.jobs import service as jobs_service
from src.jobs import tasks as job_tasks
from src.exceptions import AuthorizationError


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


def test_analysis_job_uses_bounded_rq_settings_and_logs(monkeypatch, caplog):
    captured = {}

    class FakeJob:
        id = "job-1"

        def get_status(self):
            return "queued"

    class FakeQueue:
        def enqueue(self, function, analysis_result_id, **settings):
            captured.update(
                function=function,
                analysis_result_id=analysis_result_id,
                settings=settings,
            )
            return FakeJob()

    monkeypatch.setattr(jobs_service, "get_ticket_jobs_queue", lambda: FakeQueue())
    caplog.set_level("INFO")

    job = jobs_service.enqueue_analysis_result_job("result-1")

    assert captured == {
        "function": job_tasks.analyze_analysis_result,
        "analysis_result_id": "result-1",
        "settings": {
            "job_timeout": 180,
            "result_ttl": 600,
            "failure_ttl": 86400,
            "retry": captured["settings"]["retry"],
            "meta": {"analysis_result_id": "result-1"},
        },
    }
    assert captured["settings"]["retry"].max == 2
    assert captured["settings"]["retry"].intervals == [5, 15]
    assert job.id == "job-1"
    assert "Analysis job enqueued" in caplog.text


def test_get_job_rejects_non_agent_before_reading_redis(monkeypatch, make_user):
    monkeypatch.setattr(
        jobs_service,
        "get_ticket_jobs_queue",
        lambda: pytest.fail("unauthorized users must be rejected before Redis access"),
    )

    with pytest.raises(AuthorizationError):
        jobs_service.get_job("job-1", make_user(role=constants.Role.USER))


def test_worker_task_imports_in_a_fresh_process():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src.jobs.tasks import analyze_analysis_result, route_ticket",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
