# rq business logic around jobs
from src.jobs.queue import get_ticket_jobs_queue
from src.jobs.tasks import inspect_ticket
from src.models import JobResponse, JobStatusResponse, User, Job 
from src.constants import JobStatus, translate_rq_status, Role, raw_job_to_job_response
from src.services import check_for_access
from src.services import tickets
from src.exceptions import AuthorizationError

def start_ticket_inspection_job(ticket_id: str) -> JobResponse:
    queue = get_ticket_jobs_queue()

    job = queue.enqueue(
        inspect_ticket,
        ticket_id,
        job_timeout=180,
        result_ttl=600,
    )
    return JobResponse(
        job_id=job.id,
        status=translate_rq_status(job.get_status())
    )


def get_job(job_id: str, requester: User) -> JobStatusResponse | None:
    if check_for_access(requester.role, Role.AGENT) is False:
        raise AuthorizationError("only_agents_can_view_jobs")

    queue = get_ticket_jobs_queue()
    raw_job = queue.fetch_job(job_id)
    if raw_job is None:
        return None

    ticket_id = raw_job.args[0]
    tickets.get_ticket(ticket_id, requester)

    status = translate_rq_status(raw_job.get_status())
    return JobStatusResponse(
        job_id=raw_job.id,
        status=status,
        result=raw_job.result if status is JobStatus.COMPLETED else None,
    )


def get_all_jobs(requester: User) -> list[Job] | None:
    if check_for_access(requester.role, Role.ADMIN) is False:
        raise AuthorizationError("only_admins_can_view_all_jobs")

    queue = get_ticket_jobs_queue()
    
    raw_jobs = queue.get_jobs()
    if raw_jobs is None: return None
    jobs = []
    for raw_job in raw_jobs:
        jobs.append(raw_job_to_job_response(raw_job))
    return jobs
    
