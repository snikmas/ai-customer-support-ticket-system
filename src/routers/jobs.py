from fastapi import Depends, APIRouter
from src import models
import src.models.jobs as job_models
from src.exceptions import JobNotFoundError
from src.dependencies.auth import get_current_user
from src.jobs import service
router = APIRouter(
    prefix="/jobs",
    tags=["tickets"]
)

@router.get("/{job_id}", status_code=200)
def get_job(job_id: str, requester: models.User = Depends(get_current_user)) -> job_models.JobStatusResponse:
    res = service.get_job(job_id, requester)
    if res is None:
        raise JobNotFoundError()
    return res

@router.get("/", status_code=200)
def get_all_jobs(requester: models.User = Depends(get_current_user)) -> list[job_models.JobStatusResponse]:
    return service.get_all_jobs(requester) or []
