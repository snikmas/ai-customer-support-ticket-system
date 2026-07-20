# rq business logic around jobs
from rq import Retry
from rq.exceptions import DuplicateJobError

from src.jobs.queue import get_ticket_jobs_queue, get_ticket_routing_queue
from src.jobs.tasks import inspect_ticket, route_ticket
from src.models import JobResponse, JobStatusResponse, User, Job 
from src.constants import JobStatus, logger, translate_rq_status, Role, raw_job_to_job_response
from src.exceptions import AuthorizationError

ROUTING_JOB_TIMEOUT_SECONDS = 60
ROUTING_RESULT_TTL_SECONDS = 600
ROUTING_FAILURE_TTL_SECONDS = 3600
ROUTING_RETRY_INTERVALS_SECONDS = [10, 30]
ACTIVE_ROUTING_JOB_STATUSES = {
    "created",
    "queued",
    "started",
    "deferred",
    "scheduled",
}


def _routing_job_id(ticket_id: str) -> str:
    return f"route-ticket:{ticket_id}"


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


def _get_ticket_for_requester(ticket_id: str, requester: User):
    # Import lazily so a standalone RQ worker can import src.jobs.tasks without
    # entering the services -> tickets -> jobs package cycle during startup.
    from src.services import tickets

    return tickets.get_ticket(ticket_id, requester)

def start_ticket_inspection_job(ticket_id: str) -> JobResponse:
    queue = get_ticket_jobs_queue()

    job = queue.enqueue(
        inspect_ticket,
        ticket_id,
        job_timeout=180,
        result_ttl=600,
    )
    logger.info(
        "Ticket inspection job enqueued",
        extra={"job_id": job.id, "ticket_id": ticket_id},
    )
    return JobResponse(
        job_id=job.id,
        status=translate_rq_status(job.get_status())
    )


def get_job(job_id: str, requester: User) -> JobStatusResponse | None:
    from src.services.permissions import check_for_access

    if check_for_access(requester.role, Role.AGENT) is False:
        raise AuthorizationError("only_agents_can_view_jobs")

    queue = get_ticket_jobs_queue()
    raw_job = queue.fetch_job(job_id)
    if raw_job is None:
        return None

    ticket_id = raw_job.args[0]
    _get_ticket_for_requester(ticket_id, requester)

    status = translate_rq_status(raw_job.get_status())
    return JobStatusResponse(
        job_id=raw_job.id,
        status=status,
        result=raw_job.result if status is JobStatus.COMPLETED else None,
    )


def get_all_jobs(requester: User) -> list[Job] | None:
    from src.services.permissions import check_for_access

    if check_for_access(requester.role, Role.ADMIN) is False:
        raise AuthorizationError("only_admins_can_view_all_jobs")

    queue = get_ticket_jobs_queue()
    
    raw_jobs = queue.get_jobs()
    if raw_jobs is None: return None
    jobs = []
    for raw_job in raw_jobs:
        jobs.append(raw_job_to_job_response(raw_job))
    return jobs
    
