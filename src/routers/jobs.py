from fastapi import Depends, APIRouter, HTTPException
from src import models, constants
import src.models.jobs as job_models
from src.dependencies.auth import get_current_user
from src.jobs import service
router = APIRouter(
    prefix="/jobs",
    tags=["tickets"]
)

@router.get("/{job_id}", status_code=200)
def get_job(job_id: str, requester: models.User = Depends(get_current_user)) -> job_models.JobResponse:
    try:
        res = service.get_job(job_id, requester)
    except Exception:
        raise Exception("smoe error")
    
    return res