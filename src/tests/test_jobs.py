from types import SimpleNamespace

import pytest

from src import constants
from src.jobs import service as jobs_service


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


def test_get_job_includes_result_only_after_success(monkeypatch):
    result = {"ticket_id": "ticket-1", "priority": 2}
    job = SimpleNamespace(
        id="job-1",
        result=result,
        get_status=lambda: "finished",
    )
    queue = SimpleNamespace(fetch_job=lambda job_id: job if job_id == job.id else None)
    monkeypatch.setattr(jobs_service, "get_ticket_jobs_queue", lambda: queue)

    response = jobs_service.get_job(job.id)

    assert response.result == result


def test_get_job_hides_result_while_job_is_not_finished(monkeypatch):
    job = SimpleNamespace(
        id="job-1",
        result={"partial": "must not leak"},
        get_status=lambda: "started",
    )
    queue = SimpleNamespace(fetch_job=lambda _: job)
    monkeypatch.setattr(jobs_service, "get_ticket_jobs_queue", lambda: queue)

    response = jobs_service.get_job(job.id)

    assert response.result is None
