"""Worker / queue / scheduler readiness, separate from API liveness.

``/health`` answers "is the API process alive and are its data dependencies
reachable?" It must NOT claim that background work is being processed. This
module answers the second question independently:

  * is there a fresh worker heartbeat?
  * is a fresh worker subscribed to every expected queue?
  * is a scheduler (embedded ``--with-scheduler`` or the ``rq cron`` service)
    heartbeating?
  * is the cron registry fresh?

The evaluation is a pure function so it can be unit tested without Redis; the
``collect_*`` helpers are the only Redis-aware part.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.jobs.queue import WORKER_QUEUE_ORDER

WORKER_STALE_AFTER_SECONDS = 60
SCHEDULER_STALE_AFTER_SECONDS = 90
CRON_STALE_AFTER_SECONDS = 180

CRON_REGISTRY_KEY = "rq:cron_schedulers"
SCHEDULER_KEY_PATTERN = "rq:scheduler:*"


@dataclass(frozen=True)
class WorkerSnapshot:
    name: str
    last_heartbeat: datetime | None
    queues: frozenset[str]


@dataclass(frozen=True)
class SchedulerSnapshot:
    name: str
    last_heartbeat: datetime | None


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    checks: dict[str, object] = field(default_factory=dict)


def _age_seconds(reference: datetime | None, now: datetime) -> float | None:
    if reference is None:
        return None
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return (now - reference).total_seconds()


def evaluate_readiness(
    *,
    database_ok: bool,
    redis_enabled: bool,
    redis_ok: bool,
    workers: list[WorkerSnapshot],
    schedulers: list[SchedulerSnapshot],
    cron_heartbeats: list[datetime],
    now: datetime,
    expected_queues: tuple[str, ...] = WORKER_QUEUE_ORDER,
    worker_stale_after: float = WORKER_STALE_AFTER_SECONDS,
    scheduler_stale_after: float = SCHEDULER_STALE_AFTER_SECONDS,
    cron_stale_after: float = CRON_STALE_AFTER_SECONDS,
) -> ReadinessReport:
    expected = frozenset(expected_queues)

    def is_fresh(reference: datetime | None, limit: float) -> bool:
        age = _age_seconds(reference, now)
        return age is not None and age <= limit

    fresh_workers = [
        worker
        for worker in workers
        if is_fresh(worker.last_heartbeat, worker_stale_after)
    ]
    worker_heartbeat_ok = bool(fresh_workers)
    subscribed = any(expected <= worker.queues for worker in fresh_workers)

    fresh_schedulers = [
        scheduler
        for scheduler in schedulers
        if is_fresh(scheduler.last_heartbeat, scheduler_stale_after)
    ]
    scheduler_ok = bool(fresh_schedulers)

    cron_ok = any(
        is_fresh(heartbeat, cron_stale_after) for heartbeat in cron_heartbeats
    )

    checks: dict[str, object] = {
        "database": {"ok": database_ok},
        "redis": {"ok": redis_ok, "enabled": redis_enabled},
        "worker_heartbeat": {
            "ok": worker_heartbeat_ok,
            "workers": len(workers),
            "fresh_workers": len(fresh_workers),
            "stale_after_seconds": worker_stale_after,
        },
        "queue_subscriptions": {
            "ok": subscribed,
            "expected": sorted(expected),
        },
        "scheduler_heartbeat": {
            "ok": scheduler_ok,
            "schedulers": len(schedulers),
            "fresh_schedulers": len(fresh_schedulers),
            "stale_after_seconds": scheduler_stale_after,
        },
        "cron_registry": {
            "ok": cron_ok,
            "entries": len(cron_heartbeats),
            "stale_after_seconds": cron_stale_after,
        },
    }

    # Worker/queue/scheduler/cron readiness is only meaningful when Redis is on.
    # With Redis disabled the API is "ready" for its documented local mode.
    if not redis_enabled:
        return ReadinessReport(ready=database_ok, checks=checks)

    ready = (
        database_ok
        and redis_ok
        and worker_heartbeat_ok
        and subscribed
        and scheduler_ok
        and cron_ok
    )
    return ReadinessReport(ready=ready, checks=checks)


def _scan_hashes(connection, pattern: str) -> list[dict[str, str]]:
    import redis as redis_lib

    hashes: list[dict[str, str]] = []
    for raw_key in connection.scan_iter(match=pattern):
        key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
        try:
            if connection.type(key) != b"hash" and connection.type(key) != "hash":
                continue
            raw_hash = connection.hgetall(key)
        except redis_lib.RedisError:
            continue
        hashes.append(
            {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in raw_hash.items()
            }
        )
    return hashes


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def collect_readiness(
    *,
    database_ok: bool,
    redis_enabled: bool,
    redis_ok: bool,
    connection=None,
    now: datetime | None = None,
) -> ReadinessReport:
    """Gather live worker/scheduler/cron state and evaluate readiness."""
    now = now or datetime.now(timezone.utc)

    if not (redis_enabled and redis_ok and connection is not None):
        return evaluate_readiness(
            database_ok=database_ok,
            redis_enabled=redis_enabled,
            redis_ok=redis_ok,
            workers=[],
            schedulers=[],
            cron_heartbeats=[],
            now=now,
        )

    from rq import Worker

    workers = [
        WorkerSnapshot(
            name=worker.name,
            last_heartbeat=worker.last_heartbeat,
            queues=frozenset(worker.queue_names()),
        )
        for worker in Worker.all(connection=connection)
    ]

    schedulers = [
        SchedulerSnapshot(
            name=str(entry.get("name", "unknown")),
            last_heartbeat=_parse_timestamp(entry.get("last_heartbeat")),
        )
        for entry in _scan_hashes(connection, SCHEDULER_KEY_PATTERN)
    ]

    cron_heartbeats: list[datetime] = []
    try:
        for _name, score in connection.zrange(
            CRON_REGISTRY_KEY, 0, -1, withscores=True
        ):
            cron_heartbeats.append(
                datetime.fromtimestamp(float(score), tz=timezone.utc)
            )
    except Exception:  # noqa: BLE001 - readiness must never raise
        cron_heartbeats = []

    return evaluate_readiness(
        database_ok=database_ok,
        redis_enabled=redis_enabled,
        redis_ok=redis_ok,
        workers=workers,
        schedulers=schedulers,
        cron_heartbeats=cron_heartbeats,
        now=now,
    )
