# http api layer
# router -> service -> queue -> redis
                    #-> tasks, run by worker

from fastapi import APIRouter, HTTPException
from src.jobs import start_ticket_analysis_job, get_job
router = APIRouter(
    tags=['jobs']
)

@router.post("/tickets/{ticket_id}/analysis-jobs", status_code=201)
def create_ticket_analysis_job(ticket_id: str):
    job = start_ticket_analysis_job(ticket_id)
    if job:
        return job
    raise HTTPException(400, detail="No results")
    
@router.get("/jobs/{job_id}", status_code=200)
def get_job_status(job_id: str):
    job = get_job(job_id)
    if job:
        return job
    raise HTTPException(404, detail="No results")
