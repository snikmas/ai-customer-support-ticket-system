# rq business logic around jobs
from redis import RedisError
from rq import Retry
from rq.exceptions import DuplicateJobError
from sqlalchemy.exc import OperationalError

from src.core import (
    ANALYSIS_RECONCILIATION_BATCH_SIZE,
    ROUTING_RECONCILIATION_BATCH_SIZE,
)
from src.db import (
    abandon_expired_analysis_result,
    attach_analysis_job,
    get_reconcilable_analysis_results,
    get_waiting_ticket_ids,
    mark_analysis_dispatched,
    record_analysis_reconciliation_attempts,
    record_routing_attempts,
)
from src.jobs.queue import get_ticket_jobs_queue, get_ticket_routing_queue
from src.jobs.tasks import analyze_analysis_result, route_ticket
from src.models import JobStatusResponse, User
from src.constants import (
    AnalysisStatus,
    JobStatus,
    logger,
    translate_rq_status,
    utc_now,
    Role,
    raw_job_to_job_response,
)
from src.exceptions import AuthorizationError, BadRequestError

ROUTING_JOB_TIMEOUT_SECONDS = 60
ROUTING_RESULT_TTL_SECONDS = 600
ROUTING_FAILURE_TTL_SECONDS = 3600
ROUTING_RETRY_INTERVALS_SECONDS = [10, 30]
ANALYSIS_JOB_TIMEOUT_SECONDS = 180
ANALYSIS_RESULT_TTL_SECONDS = 600
ANALYSIS_FAILURE_TTL_SECONDS = 86400
ANALYSIS_RETRY_INTERVALS_SECONDS = [10, 60]
ACTIVE_ROUTING_JOB_STATUSES = {
    "created",
    "queued",
    "started",
    "deferred",
    "scheduled",
}

# RQ job states that mean a dispatched analysis job may still make progress on
# its own. Missing data is deliberately NOT in this set: absence of a job is
# only permission to re-dispatch PENDING work, never to repeat a provider call.
ANALYSIS_ACTIVE_JOB_STATUSES = {
    "created",
    "queued",
    "started",
    "deferred",
    "scheduled",
}
ANALYSIS_LOST_JOB_STATUSES = {
    "finished",
    "failed",
    "stopped",
    "canceled",
}
# Transient infrastructure failures that leave the analysis row recoverable.
ANALYSIS_RECONCILIATION_TRANSIENT_ERRORS = (
    RedisError,
    ConnectionError,
    OperationalError,
    TimeoutError,
)


def _routing_job_id(ticket_id: str) -> str:
    # RQ 2.10 accepts only letters, numbers, underscores, and dashes in a
    # custom job ID. Keeping the ticket ID in the value still gives us one
    # stable routing-job identity per ticket without using a forbidden colon.
    return f"route-ticket-{ticket_id}"


def enqueue_ticket_routing_job(ticket_id: str):
    """Enqueue at most one active routing job for a ticket where practical.

    RQ's unique job ID closes the common duplicate-enqueue race. The database
    transaction in ``try_route_ticket`` remains the final correctness defense.
    A finished/failed prior job is deleted so reconciliation may try again.
    """
    queue = get_ticket_routing_queue()
    job_id = _routing_job_id(ticket_id)
    existing_job = queue.fetch_job(job_id)
    if existing_job is not None:
        existing_status = existing_job.get_status(refresh=True)
        status_value = getattr(existing_status, "value", existing_status)
        if status_value in ACTIVE_ROUTING_JOB_STATUSES:
            logger.info(
                "Ticket routing job already active",
                extra={"job_id": job_id, "ticket_id": ticket_id},
            )
            return existing_job
        existing_job.delete()

    try:
        job = queue.enqueue(
            route_ticket,
            ticket_id,
            job_id=job_id,
            unique=True,
            job_timeout=ROUTING_JOB_TIMEOUT_SECONDS,
            result_ttl=ROUTING_RESULT_TTL_SECONDS,
            failure_ttl=ROUTING_FAILURE_TTL_SECONDS,
            retry=Retry(
                max=len(ROUTING_RETRY_INTERVALS_SECONDS),
                interval=ROUTING_RETRY_INTERVALS_SECONDS,
            ),
        )
    except DuplicateJobError:
        # Another API process won the small fetch/enqueue race. Reuse its job;
        # if it disappeared as well, let the technical error reach the caller.
        existing_job = queue.fetch_job(job_id)
        if existing_job is None:
            raise
        logger.info(
            "Ticket routing job concurrently enqueued",
            extra={"job_id": job_id, "ticket_id": ticket_id},
        )
        return existing_job

    logger.info(
        "Ticket routing job enqueued",
        extra={"job_id": job.id, "ticket_id": ticket_id},
    )
    return job


def route_waiting_tickets(
    batch_size: int = ROUTING_RECONCILIATION_BATCH_SIZE,
) -> dict:
    """Enqueue one bounded, fair page of waiting tickets.

    The scan is ordered by least-recently-attempted (never-attempted first), so
    no-eligible-agent tickets rotate instead of blocking later tickets. With W
    waiting tickets and batch size B, a stable waiting set is fully visited once
    per ``ceil(W / B)`` passes; that is the finite recovery bound. Successfully
    dispatched tickets are stamped with one bounded write after the read session
    has closed, so no database session spans the Redis enqueues. A Redis failure
    for one ticket is reported and does not roll back the read or prevent later
    tickets in the same page from being tried.
    """
    if batch_size <= 0:
        raise BadRequestError(
            "Batch size must be greater than zero",
            code="invalid_batch_size",
        )

    ticket_ids = get_waiting_ticket_ids(batch_size)
    enqueued_ticket_ids = []
    failed_ticket_ids = []

    for ticket_id in ticket_ids:
        try:
            enqueue_ticket_routing_job(ticket_id)
        except Exception:
            failed_ticket_ids.append(ticket_id)
            logger.exception(
                "Waiting ticket routing enqueue failed",
                extra={"ticket_id": ticket_id},
            )
        else:
            enqueued_ticket_ids.append(ticket_id)

    result = {
        "selected_count": len(ticket_ids),
        "enqueued_count": len(enqueued_ticket_ids),
        "failed_count": len(failed_ticket_ids),
        "enqueued_ticket_ids": enqueued_ticket_ids,
        "failed_ticket_ids": failed_ticket_ids,
    }
    _record_dispatched_attempts(enqueued_ticket_ids)
    logger.info("Waiting ticket routing dispatch completed", extra=result)
    return result


def _record_dispatched_attempts(ticket_ids: list[str]) -> None:
    """Best-effort durable stamp so dispatched tickets rotate behind the rest.

    The read session is already closed and the enqueues are already done, so
    this short write never spans Redis work. A failure only means the same page
    may be reconsidered on the next pass; it can delay a retry, never drop one.
    """
    if not ticket_ids:
        return
    try:
        record_routing_attempts(ticket_ids, utc_now())
    except Exception:
        logger.exception(
            "Recording routing attempts failed",
            extra={"ticket_count": len(ticket_ids)},
        )


def _get_ticket_for_requester(ticket_id: str, requester: User):
    # Import lazily so a standalone RQ worker can import src.jobs.tasks without
    # entering the services -> tickets -> jobs package cycle during startup.
    from src.services import tickets

    return tickets.get_ticket(ticket_id, requester)

def _analysis_job_id(analysis_result_id: str) -> str:
    # A stable identity makes dispatch idempotent: every dispatch path for a
    # given analysis result competes for the same RQ job ID, so two reconcilers
    # cannot create two ACTIVE executions. RQ allows only letters, numbers,
    # underscores, and dashes in a custom job ID.
    return f"analyze-result-{analysis_result_id}"


def _job_status_value(raw_job) -> str:
    status = raw_job.get_status(refresh=True)
    return getattr(status, "value", status)


def reconcile_analysis_results(
    batch_size: int = ANALYSIS_RECONCILIATION_BATCH_SIZE,
) -> dict:
    """Bounded recovery pass over interrupted analysis work.

    It only re-dispatches PENDING rows whose RQ job was never created or was
    lost. A RUNNING row is never re-dispatched: if its lease is expired it is
    moved to the safe terminal ``provider_result_unknown`` state so a human can
    decide whether to retry a possibly billed provider call. Terminal rows are
    never selected, so expired RQ results cannot resurrect completed work.
    """
    if batch_size <= 0:
        raise BadRequestError(
            "Batch size must be greater than zero",
            code="invalid_batch_size",
        )

    now = utc_now()
    rows = get_reconcilable_analysis_results(batch_size, now)
    summary = {
        "considered": len(rows),
        "left_live": 0,
        "redispatched": 0,
        "linked": 0,
        "abandoned": 0,
        "redis_unavailable": 0,
        "skipped": 0,
    }
    considered_ids: list[str] = []

    for row in rows:
        try:
            if row.status is AnalysisStatus.PENDING:
                outcome = _reconcile_pending_analysis(row, now)
            else:
                outcome = _reconcile_abandoned_analysis(row, now)
        except ANALYSIS_RECONCILIATION_TRANSIENT_ERRORS:
            # Redis is unavailable: leave the row exactly as it is. The next
            # scheduled pass is the backoff, and the durable SQL row still
            # records the work that needs dispatch. Do NOT stamp it: we never
            # observed its job state, so deferring it would only delay recovery.
            summary["redis_unavailable"] += 1
            logger.warning(
                "Analysis reconciliation deferred: Redis unavailable",
                extra={"analysis_result_id": row.id},
            )
            continue
        summary[outcome] += 1
        considered_ids.append(row.id)

    # Rotate the rows actually considered behind never-considered work so a live
    # job on an older PENDING row cannot starve later recoverable rows. This is
    # a bounded single UPDATE over the ids this pass read; a lost write defers a
    # retry by at most one rotation.
    _record_reconciliation_attempts(considered_ids, now)

    logger.info("Analysis reconciliation completed", extra=summary)
    return summary


def _record_reconciliation_attempts(analysis_result_ids: list[str], now) -> None:
    if not analysis_result_ids:
        return
    try:
        record_analysis_reconciliation_attempts(analysis_result_ids, now)
    except Exception:
        logger.exception(
            "Recording analysis reconciliation attempts failed",
            extra={"analysis_result_count": len(analysis_result_ids)},
        )


def _reconcile_pending_analysis(row, now):
    queue = get_ticket_jobs_queue()
    job_id = _analysis_job_id(row.id)
    job = queue.fetch_job(job_id)
    state = _job_status_value(job) if job is not None else None

    if job is not None and state in ANALYSIS_ACTIVE_JOB_STATUSES:
        # A queued/scheduled/live job already owns the work. Only repair a
        # missing job link; never add a second execution.
        if row.job_id is None:
            attached = attach_analysis_job(row.id, job_id, now)
            if attached is not None:
                return "linked"
        return "left_live"

    # Job missing, finished, or failed. The row is PENDING, so any prior
    # provider attempt ended in a known failure. Re-dispatch is safe and the
    # stable job ID makes it idempotent under concurrent reconcilers.
    job = enqueue_analysis_result_job(row.id)
    updated = mark_analysis_dispatched(row.id, job.id, now)
    return "redispatched" if updated is not None else "skipped"


def _reconcile_abandoned_analysis(row, now):
    if row.lease_expires_at is not None and row.lease_expires_at > now:
        # A healthy slow attempt still owns the row. Do not touch it.
        return "left_live"

    # The owner's lease expired. The provider call may have completed and been
    # billed, so repeating it automatically is unsafe. Reach an explicit
    # terminal state and require a human-initiated retry instead. The write is
    # conditional on the execution_id this pass observed, so a newer live
    # attempt that replaced the stale one is never failed.
    updated = abandon_expired_analysis_result(
        row.id,
        execution_id=row.execution_id,
        error_code="provider_result_unknown",
        error_message="Analysis worker was interrupted; provider result is unknown",
        now=now,
    )
    if updated is None:
        return "skipped"
    logger.warning(
        "Abandoned analysis moved to safe terminal state",
        extra={"analysis_result_id": row.id},
    )
    return "abandoned"


def enqueue_analysis_result_job(analysis_result_id: str):
    """Enqueue the single stable analysis job for a result.

    RQ's unique stable job ID closes the duplicate-dispatch race. A finished or
    failed prior job is deleted so a fresh dispatch may take its place.
    """
    queue = get_ticket_jobs_queue()
    job_id = _analysis_job_id(analysis_result_id)
    existing_job = queue.fetch_job(job_id)
    if existing_job is not None:
        if _job_status_value(existing_job) in ANALYSIS_ACTIVE_JOB_STATUSES:
            logger.info(
                "Analysis job already active",
                extra={"job_id": job_id, "analysis_result_id": analysis_result_id},
            )
            return existing_job
        existing_job.delete()

    try:
        job = queue.enqueue(
            analyze_analysis_result,
            analysis_result_id,
            job_id=job_id,
            unique=True,
            job_timeout=ANALYSIS_JOB_TIMEOUT_SECONDS,
            result_ttl=ANALYSIS_RESULT_TTL_SECONDS,
            failure_ttl=ANALYSIS_FAILURE_TTL_SECONDS,
            retry=Retry(
                max=len(ANALYSIS_RETRY_INTERVALS_SECONDS),
                interval=ANALYSIS_RETRY_INTERVALS_SECONDS,
            ),
            meta={"analysis_result_id": analysis_result_id},
        )
    except DuplicateJobError:
        existing_job = queue.fetch_job(job_id)
        if existing_job is None:
            raise
        logger.info(
            "Analysis job concurrently enqueued",
            extra={"job_id": job_id, "analysis_result_id": analysis_result_id},
        )
        return existing_job

    logger.info(
        "Analysis job enqueued",
        extra={"job_id": job.id, "analysis_result_id": analysis_result_id},
    )
    return job


def get_job(job_id: str, requester: User) -> JobStatusResponse | None:
    from src.services.permissions import check_for_access

    if check_for_access(requester.role, Role.AGENT) is False:
        raise AuthorizationError("Only agents can view jobs", code="only_agents_can_view_jobs")

    queue = get_ticket_jobs_queue()
    raw_job = queue.fetch_job(job_id)
    if raw_job is None:
        return None

    analysis_result_id = getattr(raw_job, "meta", {}).get("analysis_result_id")
    if analysis_result_id is not None:
        from src.services.analysis_results import get_analysis_result

        get_analysis_result(analysis_result_id, requester)
    elif raw_job.args:
        ticket_id = raw_job.args[0]
        _get_ticket_for_requester(ticket_id, requester)
    # Cron-enqueued jobs (e.g., route_waiting_tickets, scan_overdue_tickets)
    # carry only kwargs, so there is no specific ticket/analysis result to
    # authorize against beyond the agent role check above.

    status = translate_rq_status(raw_job.get_status())
    return JobStatusResponse(
        job_id=raw_job.id,
        status=status,
        result=raw_job.result if status is JobStatus.COMPLETED else None,
    )


def get_all_jobs(requester: User) -> list[JobStatusResponse] | None:
    from src.services.permissions import check_for_access

    if check_for_access(requester.role, Role.ADMIN) is False:
        raise AuthorizationError("Only administrators can view all jobs", code="only_admins_can_view_all_jobs")

    queue = get_ticket_jobs_queue()
    
    raw_jobs = queue.get_jobs()
    if raw_jobs is None:
        return None
    jobs = []
    for raw_job in raw_jobs:
        jobs.append(raw_job_to_job_response(raw_job))
    return jobs
    
