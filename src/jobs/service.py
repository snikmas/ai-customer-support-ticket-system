# business logic around jobs
from rq import Queue
from src.jobs.queue import get_ticket_analysis_queue
from src.constants import generate_id
from src.jobs.tasks import analyze_ticket

def start_ticket_analysis_job(ticket_id: str):
    queue = get_ticket_analysis_queue()
    job = queue.enqueue(analyze_ticket, ticket_id)

    job = {
        "id": generate_id(),
        "title": b"job",
        "status": None
    }
    job = queue,enqueue(ticket_id)
    return job

def get_job(job_id: str) -> Job | None:
    queue = get_ticket_analysis_queue()
    job = queue.fetch_job(ticket_id)
    return job