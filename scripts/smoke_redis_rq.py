#!/usr/bin/env python
"""Real Redis/RQ + fake-provider smoke for the analysis lifecycle.

This is the Phase I integration gate that the unit tests cannot give: it uses a
real Redis server and a real RQ worker (``rq.SimpleWorker``) instead of a fake
queue, and it exercises the Phase E recovery reconciler against real Redis job
state.

It is deliberately self-contained and disposable:

* It requires a *task-owned* Redis. To avoid clobbering a developer's cache it
  refuses a non-loopback host unless ``SMOKE_ALLOW_REMOTE=1`` is set. It never
  calls ``FLUSHDB``: it enqueues onto a run-unique queue name and, at the end,
  deletes only the Redis keys (queue list, job hashes, registry entries, worker
  registration) that this run created, so an application queue on the same
  server is untouched.
* It uses a temporary SQLite database (or ``SMOKE_DATABASE_URL``) and a local
  fake analyzer, so it never contacts a provider and never touches the normal
  project database.
* Every wait is bounded; a stuck worker fails the smoke instead of hanging CI.

Scenarios (all must reach a documented state):
1. Happy path: PENDING -> real RQ worker -> COMPLETED with the fake summary.
2. Lost job: a persisted job link whose Redis job disappeared is re-dispatched
   by the reconciler, then completes.
3. Two reconcilers do not create a second active execution.
4. Abandoned RUNNING work (expired lease) reaches the safe terminal
   ``provider_result_unknown`` state.

Exit code 0 means every scenario passed.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

# Allow ``python scripts/smoke_redis_rq.py`` (which puts ``scripts/`` rather
# than the repository root on ``sys.path``) as well as ``python -m ...``.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_REDIS_URL = "redis://127.0.0.1:56379/0"
SCENARIO_TIMEOUT_SECONDS = 30.0

FAKE_PROVIDER = "fake"
FAKE_MODEL = "deterministic-fake-v1"
FAKE_PROMPT_VERSION = "ticket_summary_v1"


class SmokeFailure(AssertionError):
    """Raised when a scenario does not reach its documented state."""


@dataclass
class Settings:
    redis_url: str
    database_url: str
    keep_database: bool


def _parse_args(argv: list[str]) -> Settings:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--redis-url",
        default=os.getenv("SMOKE_REDIS_URL") or DEFAULT_REDIS_URL,
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("SMOKE_DATABASE_URL"),
        help="Optional database URL; defaults to a temporary SQLite file.",
    )
    parser.add_argument(
        "--keep-database",
        action="store_true",
        help="Do not delete the temporary SQLite file on exit.",
    )
    args = parser.parse_args(argv)
    return Settings(
        redis_url=args.redis_url,
        database_url=args.database_url,
        keep_database=args.keep_database,
    )


def _assert_loopback_redis(redis_url: str) -> None:
    host = urlsplit(redis_url).hostname or ""
    if host in {"127.0.0.1", "localhost", "::1"}:
        return
    if os.getenv("SMOKE_ALLOW_REMOTE") == "1":
        return
    raise SystemExit(
        f"Refusing to run against non-loopback Redis host {host!r}. "
        "Set SMOKE_ALLOW_REMOTE=1 if this really is a disposable server."
    )


def _configure_environment(settings: Settings, temp_dir: str) -> str:
    """Set the project environment before importing ``src``.

    ``PYTHON_DOTENV_DISABLED`` stops ``src.core.config`` from reading a
    developer's private ``.env``. The fake provider and Redis-on settings keep
    the run synthetic and local.
    """
    database_url = settings.database_url or (
        f"sqlite+pysqlite:///{os.path.join(temp_dir, 'smoke-redis-rq.db')}"
    )
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["DATABASE_URL"] = database_url
    os.environ["DATABASE_ECHO"] = "false"
    os.environ["REDIS_ENABLED"] = "true"
    os.environ["REDIS_URL"] = settings.redis_url
    os.environ["ANALYZER_PROVIDER"] = FAKE_PROVIDER
    os.environ["FAKE_ANALYZER_DELAY_SECONDS"] = "0"
    os.environ["FAKE_ANALYZER_FAILURE_MODE"] = "none"
    # Attribution keys are never used by the fake provider, but they must be
    # configured so the run does not fall back to a developer's real values.
    os.environ["REFRESH_TOKEN_SECRET"] = "smoke-refresh-token-secret"
    os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ.pop("OPENROUTER_API_KEY", None)
    return database_url


def _wait_until(predicate, *, timeout: float, interval: float = 0.1):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    return last


def _seed_ticket(engine, constants, Ticket, User, ticket_id: str) -> str:
    from sqlalchemy.orm import Session

    now = datetime.now(timezone.utc)
    creator_id = f"smoke-user-{time.time_ns()}"
    with Session(engine) as session:
        session.add(
            User(
                id=creator_id,
                nickname=f"smoke{time.time_ns() % 1_000_000_000}",
                avatar_url=None,
                first_name="Smoke",
                last_name="Customer",
                phone="+15550009999",
                email=f"{creator_id}@example.invalid",
                password="not-a-real-hash",
                role=constants.Role.USER,
                user_status=constants.UserStatus.ACTIVE,
                deleted_at=None,
                updated_at=now,
                created_at=now,
            )
        )
        session.flush()
        session.add(
            Ticket(
                id=ticket_id,
                title="Smoke payment failure",
                description="Synthetic card payment returns error 500",
                category=constants.Category.BILLING,
                tags=constants.serialize_tags([constants.Tag.ERROR_500]),
                department_id=None,
                assigned_agent_id=None,
                creator_user_id=creator_id,
                status=constants.Status.IN_PROGRESS,
                priority=constants.Priority.HIGH,
                updated_at=now,
                created_at=now,
                due_at=None,
                deleted_at=None,
            )
        )
        session.commit()
    return creator_id


def _pending_row(operations, DbAnalysisResult, AnalysisInputSnapshot, constants, *,
                 result_id: str, ticket_id: str):
    now = datetime.now(timezone.utc)
    snapshot = AnalysisInputSnapshot(
        title="Smoke payment failure",
        description="Synthetic card payment returns error 500",
        category=constants.Category.BILLING,
        tags=(constants.Tag.ERROR_500,),
        priority=constants.Priority.HIGH,
        status=constants.Status.IN_PROGRESS,
    )
    return operations.create_analysis_result(
        DbAnalysisResult(
            id=result_id,
            input_snapshot=snapshot.model_dump_json(),
            summary=None,
            error_code=None,
            error_message=None,
            ticket_id=ticket_id,
            job_id=None,
            provider=FAKE_PROVIDER,
            model=FAKE_MODEL,
            prompt_version=FAKE_PROMPT_VERSION,
            input_tokens=None,
            output_tokens=None,
            requester_id=None,
            attempt_count=0,
            created_at=now,
            started_at=None,
            completed_at=None,
            updated_at=now,
            status=constants.AnalysisStatus.PENDING,
        )
    )


def _run_worker_burst(context) -> None:
    worker = context.SimpleWorker([context.queue], connection=context.queue.connection)
    worker.work(burst=True)
    context.worker_names.append(worker.name)


# Registries RQ updates with a job id. RQ names them either globally
# (``rq:finished``) or per-queue (``rq:finished:<queue>``), so cleanup removes
# this run's job ids from both forms and deletes the owned per-queue key.
_OWNED_REGISTRY_NAMES = ("finished", "started", "failed", "deferred", "scheduled")


def _owned_queue_name() -> str:
    """A queue name unique to this run, so cleanup never touches app queues."""
    return f"ticket_jobs_smoke_{uuid4().hex}"


def _cleanup_owned_keys(client, *, queue_name: str, result_ids, worker_names) -> None:
    """Delete only the Redis keys this smoke run created.

    No ``FLUSHDB``: the queue list, this run's job and result hashes, its
    entries in the registries, and its worker registration are removed by name,
    so a real application queue on the same Redis server is left intact.
    """
    from src.jobs.service import _analysis_job_id

    keys = [f"rq:queue:{queue_name}"]
    for registry in _OWNED_REGISTRY_NAMES:
        keys.append(f"rq:{registry}:{queue_name}")
    for result_id in result_ids:
        job_id = _analysis_job_id(result_id)
        keys.extend((f"rq:job:{job_id}", f"rq:results:{job_id}", f"rq:result:{job_id}"))
        for registry in _OWNED_REGISTRY_NAMES:
            client.zrem(f"rq:{registry}", job_id)
            client.zrem(f"rq:{registry}:{queue_name}", job_id)
    for worker_name in worker_names:
        keys.append(f"rq:worker:{worker_name}")
        client.srem("rq:workers", worker_name)
    client.delete(*keys)
    # RQ stores queue *keys* (``rq:queue:<name>``) in the ``rq:queues`` set.
    client.srem("rq:queues", f"rq:queue:{queue_name}")


def _scenario_happy_path(context) -> None:
    operations = context.operations
    result_id = f"smoke-happy-{time.time_ns()}"
    context.created_result_ids.append(result_id)
    row = _pending_row(
        operations,
        context.DbAnalysisResult,
        context.AnalysisInputSnapshot,
        context.constants,
        result_id=result_id,
        ticket_id=context.ticket_id,
    )
    job = context.jobs_service.enqueue_analysis_result_job(row.id)
    if job is None:
        raise SmokeFailure("happy path: enqueue returned no job")
    _run_worker_burst(context)

    stored = _wait_until(
        lambda: (
            context.operations.get_analysis_result(row.id)
            if _status_is_terminal(context.operations.get_analysis_result(row.id), context.constants)
            else None
        ),
        timeout=SCENARIO_TIMEOUT_SECONDS,
    )
    if stored is None:
        raise SmokeFailure("happy path: analysis never reached a terminal state")
    if stored.status is not context.constants.AnalysisStatus.COMPLETED:
        raise SmokeFailure(
            f"happy path: expected COMPLETED, got {stored.status}: {stored.error_code}"
        )
    if not stored.summary:
        raise SmokeFailure("happy path: completed row has no summary")
    print(f"PASS happy path: {row.id} -> COMPLETED ({stored.summary[:40]!r}...)")


def _status_is_terminal(row, constants) -> bool:
    if row is None:
        return False
    return row.status in {
        constants.AnalysisStatus.COMPLETED,
        constants.AnalysisStatus.FAILED,
    }


def _scenario_lost_job_recovery(context) -> None:
    result_id = f"smoke-lost-{time.time_ns()}"
    context.created_result_ids.append(result_id)
    row = _pending_row(
        context.operations,
        context.DbAnalysisResult,
        context.AnalysisInputSnapshot,
        context.constants,
        result_id=result_id,
        ticket_id=context.ticket_id,
    )
    job = context.jobs_service.enqueue_analysis_result_job(row.id)
    now = datetime.now(timezone.utc)
    if context.operations.attach_analysis_job(row.id, job.id, now) is None:
        raise SmokeFailure("lost job: could not persist the job link")

    # Simulate Redis losing the job while SQL still records the dispatch.
    stale = context.queue.fetch_job(job.id)
    if stale is None:
        raise SmokeFailure("lost job: expected an enqueued job to delete")
    stale.delete()

    summary = context.jobs_service.reconcile_analysis_results(batch_size=10)
    if summary["redispatched"] < 1:
        raise SmokeFailure(f"lost job: reconciler did not redispatch ({summary})")

    _run_worker_burst(context)
    stored = _wait_until(
        lambda: (
            context.operations.get_analysis_result(row.id)
            if _status_is_terminal(context.operations.get_analysis_result(row.id), context.constants)
            else None
        ),
        timeout=SCENARIO_TIMEOUT_SECONDS,
    )
    if stored is None or stored.status is not context.constants.AnalysisStatus.COMPLETED:
        raise SmokeFailure("lost job: recovered work did not complete")
    print(f"PASS lost-job recovery: redispatch={summary['redispatched']} -> COMPLETED")


def _scenario_two_reconcilers(context) -> None:
    result_id = f"smoke-race-{time.time_ns()}"
    context.created_result_ids.append(result_id)
    row = _pending_row(
        context.operations,
        context.DbAnalysisResult,
        context.AnalysisInputSnapshot,
        context.constants,
        result_id=result_id,
        ticket_id=context.ticket_id,
    )
    stable_id = context.jobs_service._analysis_job_id(row.id)
    first = context.jobs_service.reconcile_analysis_results(batch_size=10)
    second = context.jobs_service.reconcile_analysis_results(batch_size=10)

    active = [
        job
        for job in [context.queue.fetch_job(stable_id)]
        if job is not None
        and _job_status(job) in context.jobs_service.ANALYSIS_ACTIVE_JOB_STATUSES
    ]
    if len(active) != 1:
        raise SmokeFailure(
            f"reconciler race: expected exactly one active job, found {len(active)}"
        )
    stored = context.operations.get_analysis_result(row.id)
    if stored.dispatch_count != 1:
        raise SmokeFailure(
            f"reconciler race: expected dispatch_count=1, got {stored.dispatch_count}"
        )
    print(
        "PASS two reconcilers: one active execution "
        f"(first={first['redispatched']}, second={second['left_live']})"
    )
    # Drain the dispatched job so later scenarios start from a clean queue.
    _run_worker_burst(context)


def _job_status(job) -> str:
    status = job.get_status(refresh=True)
    return getattr(status, "value", status)


def _scenario_abandoned_running(context) -> None:
    result_id = f"smoke-abandoned-{time.time_ns()}"
    context.created_result_ids.append(result_id)
    row = _pending_row(
        context.operations,
        context.DbAnalysisResult,
        context.AnalysisInputSnapshot,
        context.constants,
        result_id=result_id,
        ticket_id=context.ticket_id,
    )
    running = context.operations.start_analysis_attempt(
        row.id,
        datetime.now(timezone.utc),
        lease_seconds=0,
    )
    if running is None or running.status is not context.constants.AnalysisStatus.RUNNING:
        raise SmokeFailure("abandoned: could not move the row to RUNNING")

    summary = context.jobs_service.reconcile_analysis_results(batch_size=10)
    if summary["abandoned"] < 1:
        raise SmokeFailure(f"abandoned: reconciler did not abandon the row ({summary})")

    stored = context.operations.get_analysis_result(row.id)
    if stored.status is not context.constants.AnalysisStatus.FAILED:
        raise SmokeFailure(f"abandoned: expected FAILED, got {stored.status}")
    if stored.error_code != "provider_result_unknown":
        raise SmokeFailure(
            f"abandoned: expected provider_result_unknown, got {stored.error_code}"
        )
    print("PASS abandoned RUNNING -> FAILED/provider_result_unknown")


def _run_scenarios(settings: Settings) -> None:
    from types import SimpleNamespace

    from rq import Queue, SimpleWorker

    from src import constants
    from src.analyzers import AnalysisInputSnapshot
    from src.db import operations
    from src.db.engine import engine
    from src.db.models import AnalysisResult as DbAnalysisResult
    from src.db.models import Base, Ticket, User
    from src.jobs import service as jobs_service

    # Fail fast with an explicit message instead of a long RQ timeout if Redis
    # is not actually reachable.
    from src.cache import get_redis_client

    client = get_redis_client()
    try:
        if not client.ping():
            raise SmokeFailure("Redis did not answer PING")
    except Exception as exc:  # noqa: BLE001 - report the concrete connection error
        raise SmokeFailure(f"cannot reach Redis at {settings.redis_url}: {exc}") from exc

    Base.metadata.create_all(engine)
    ticket_id = f"smoke-ticket-{time.time_ns()}"
    _seed_ticket(engine, constants, Ticket, User, ticket_id)

    # Use a run-unique queue so an application ``ticket_jobs`` queue on the
    # same server is never touched. The reconciler creates jobs through
    # ``jobs_service.get_ticket_jobs_queue``, so point that at the owned queue.
    queue = Queue(_owned_queue_name(), connection=client)
    jobs_service.get_ticket_jobs_queue = lambda: queue
    context = SimpleNamespace(
        constants=constants,
        operations=operations,
        DbAnalysisResult=DbAnalysisResult,
        AnalysisInputSnapshot=AnalysisInputSnapshot,
        jobs_service=jobs_service,
        queue=queue,
        SimpleWorker=SimpleWorker,
        ticket_id=ticket_id,
        created_result_ids=[],
        worker_names=[],
    )

    _scenario_happy_path(context)
    _scenario_lost_job_recovery(context)
    _scenario_two_reconcilers(context)
    _scenario_abandoned_running(context)

    # Cleanup: delete only the keys this run created (its queue list, job
    # hashes, registry entries, and worker registration). No FLUSHDB, so a
    # shared Redis server is safe.
    try:
        _cleanup_owned_keys(
            client,
            queue_name=queue.name,
            result_ids=context.created_result_ids,
            worker_names=context.worker_names,
        )
    except Exception as exc:  # noqa: BLE001 - cleanup is best-effort
        print(f"WARN: could not clean smoke Redis keys: {exc}", file=sys.stderr)
    engine.dispose()


def main(argv: list[str] | None = None) -> int:
    settings = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    _assert_loopback_redis(settings.redis_url)

    with tempfile.TemporaryDirectory(prefix="resolveai-smoke-") as temp_dir:
        database_url = _configure_environment(settings, temp_dir)
        keep = settings.keep_database and settings.database_url is None
        try:
            _run_scenarios(settings)
        except SmokeFailure as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        if keep:
            print(f"INFO: temporary database kept at {database_url}")
    print("All Redis/RQ smoke scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
