from pydantic import BaseModel
from src.constants.enums import JobStatus

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus

class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    result: dict | None = None
    error: str | None = None

class Job(BaseModel):
    id: str
    func_name: str
    status: str
    result: str
    created_at: str
    enqueued_at: str
    ended_at: str