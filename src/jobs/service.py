# rq business logic around jobs
from rq.job import Job
from src.jobs.queue import get_ticket_analysis_queue, get_inspect_ticket_queue
from src.jobs.tasks import analyze_ticket
from src.models import JobResponse, JobStatusResponse, User
from src.constants import translate_rq_status, Role
from src.db import get_ticket, get_user
from src.exceptions import TicketNotFoundError, AuthenticationError, AuthorizationError
from src.services import check_for_access

# GPT: okay now this queu is just to checkL can we do basic stuff
def start_ticket_inspection_job(ticket_id: str):
    queue = get_inspect_ticket_queue()

    job = queue.enqueue(
        'inspect_ticket',
        ticket_id,
        job_timeout=180,
        result_ttl=600 
        
    )
    return JobResponse(
        job_id=job.id,
        status=translate_rq_status(job.get_status())
    )
    

def start_ticket_analysis_job(ticket_id: str, requester: User) -> JobResponse | None:
    ticket = get_ticket(ticket_id)
    if ticket is None: raise TicketNotFoundError
    if ticket.creator_user_id != requester.id: raise AuthorizationError
    if check_for_access(requester.role, Role.USER) is False: return AuthenticationError

    queue = get_ticket_analysis_queue()
    job = queue.enqueue(analyze_ticket, ticket_id)
    if job:
        return JobResponse(
            job_id=job.id, 
            status=translate_rq_status(job.get_status())
        )
    return None

def get_job(job_id: str) -> JobStatusResponse | None:
    queue = get_ticket_analysis_queue()
    job = queue.fetch_job(job_id)
    if job:
        return JobStatusResponse(
        job_id=job.id,
        status=translate_rq_status(job.get_status())
        )
    return None