from fastapi import APIRouter, Depends, Query

from src import constants, models
from src.dependencies.auth import get_current_user
from src.services import notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", status_code=200)
def list_notifications(
    requester: models.User = Depends(get_current_user),
    limit: int = Query(constants.DEFAULT_PAGE_LIMIT, ge=1, le=constants.MAX_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
    unread_only: bool = False,
):
    return {"data": notifications.list_for_user(requester, limit, offset, unread_only)}


@router.get("/unread-count", status_code=200)
def unread_count(requester: models.User = Depends(get_current_user)):
    return {"data": {"count": notifications.unread_count(requester)}}


@router.patch("/{notification_id}", status_code=200)
def mark_read(
    notification_id: str,
    requester: models.User = Depends(get_current_user),
):
    return {"data": notifications.mark_read(notification_id, requester)}


@router.post("/read-all", status_code=200)
def mark_all_read(requester: models.User = Depends(get_current_user)):
    return {"data": {"updated": notifications.mark_all_read(requester)}}
