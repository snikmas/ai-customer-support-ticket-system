# rq business logic around jobs
from rq.job import Job
from src.jobs.queue import get_ticket_analysis_queue
from src.jobs.tasks import analyze_ticket
from src.models import JobResponse, JobStatusResponse
from src.constants import translate_rq_status

def start_ticket_analysis_job(ticket_id: str) -> JobResponse | None:
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