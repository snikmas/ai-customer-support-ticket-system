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
