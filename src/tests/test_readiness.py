"""Readiness evaluation is a pure function so it needs no live Redis."""

from datetime import datetime, timedelta, timezone

from src.jobs.queue import WORKER_QUEUE_ORDER
from src.jobs.readiness import (
    SchedulerSnapshot,
    WorkerSnapshot,
    evaluate_readiness,
)

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def _worker(*, age_seconds=0, queues=WORKER_QUEUE_ORDER):
    return WorkerSnapshot(
        name="worker-1",
        last_heartbeat=NOW - timedelta(seconds=age_seconds),
        queues=frozenset(queues),
    )


def _scheduler(*, age_seconds=0):
    return SchedulerSnapshot(
        name="scheduler-1",
        last_heartbeat=NOW - timedelta(seconds=age_seconds),
    )


def _report(**overrides):
    base = dict(
        database_ok=True,
        redis_enabled=True,
        redis_ok=True,
        workers=[_worker()],
        schedulers=[_scheduler()],
        cron_heartbeats=[NOW],
        now=NOW,
    )
    base.update(overrides)
    return evaluate_readiness(**base)


def test_all_fresh_components_are_ready():
    report = _report()
    assert report.ready is True
    assert report.checks["worker_heartbeat"]["ok"] is True
    assert report.checks["queue_subscriptions"]["ok"] is True
    assert report.checks["scheduler_heartbeat"]["ok"] is True
    assert report.checks["cron_registry"]["ok"] is True


def test_missing_worker_is_not_ready_but_health_would_be():
    report = _report(workers=[])
    assert report.ready is False
    assert report.checks["worker_heartbeat"]["ok"] is False


def test_stale_worker_heartbeat_is_not_ready():
    report = _report(workers=[_worker(age_seconds=600)])
    assert report.ready is False
    assert report.checks["worker_heartbeat"]["fresh_workers"] == 0


def test_worker_not_subscribed_to_every_queue_is_not_ready():
    report = _report(workers=[_worker(queues=("ticket_jobs",))])
    assert report.ready is False
    assert report.checks["queue_subscriptions"]["ok"] is False


def test_stale_scheduler_is_not_ready():
    report = _report(schedulers=[_scheduler(age_seconds=600)])
    assert report.ready is False
    assert report.checks["scheduler_heartbeat"]["ok"] is False


def test_stale_cron_registry_is_not_ready():
    report = _report(cron_heartbeats=[NOW - timedelta(hours=1)])
    assert report.ready is False
    assert report.checks["cron_registry"]["ok"] is False


def test_redis_disabled_readiness_tracks_database_only():
    ready = _report(redis_enabled=False, redis_ok=False, workers=[])
    assert ready.ready is True
    down = _report(redis_enabled=False, redis_ok=False, workers=[], database_ok=False)
    assert down.ready is False
