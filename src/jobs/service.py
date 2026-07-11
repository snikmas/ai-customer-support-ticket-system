# rq business logic around jobs
from rq.job import Job
from src.jobs.queue import get_ticket_jobs_queue
from src.jobs.tasks import inspect_ticket
from src.models import JobResponse, JobStatusResponse
from src.constants import translate_rq_status

def start_ticket_inspection_job(ticket_id: str):
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


def get_job(job_id: str) -> JobStatusResponse | None:
    queue = get_ticket_jobs_queue()
    job = queue.fetch_job(job_id)
    if job:
        return JobStatusResponse(
            job_id=job.id,
            status=translate_rq_status(job.get_status())
        )
    return None
