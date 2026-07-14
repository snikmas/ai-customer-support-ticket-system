from fastapi import Depends, APIRouter, HTTPException
from src import models, constants
import src.models.jobs as job_models
from src.exceptions import NotFoundError, AuthenticationError, AuthorizationError
from src.dependencies.auth import get_current_user
from src.jobs import service
router = APIRouter(
    prefix="/jobs",
    tags=["tickets"]
)

@router.get("/{job_id}", status_code=200)
def get_job(job_id: str, requester: models.User = Depends(get_current_user)) -> job_models.JobStatusResponse:
    try:
        res = service.get_job(job_id, requester)
    except NotFoundError:
        raise HTTPException(404, detail="Job Doesn't Exist")
    except AuthorizationError:
        raise HTTPException(404, detail="Authorization Error")
    except AuthenticationError:
        raise HTTPException(404, detail="Authentication Error")
    
    return res

@router.get("/", status_code=200)
def get_all_jobs(requester: models.User = Depends(get_current_user)) -> list[job_models.JobStatusResponse]:
    try:
        res = service.get_all_jobs(requester)
    except NotFoundError:
        raise HTTPException(404, detail="Job Doesn't Exist")
    except AuthorizationError:
        raise HTTPException(404, detail="Authorization Error")
    except AuthenticationError:
        raise HTTPException(404, detail="Authentication Error")
    
    return res