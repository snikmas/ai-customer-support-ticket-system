from fastapi import APIRouter, Depends

from src import models
from src.dependencies.auth import get_current_user
from src.services import ai_settings


router = APIRouter(prefix="/ai-settings", tags=["ai-settings"])


@router.get("/", status_code=200)
def get_ai_settings(requester: models.User = Depends(get_current_user)):
    return {"data": ai_settings.get_settings(requester)}


@router.patch("/", status_code=200)
def update_ai_settings(
    data: models.AISettingsUpdate,
    requester: models.User = Depends(get_current_user),
):
    return {"data": ai_settings.update_settings(data, requester)}


@router.post("/test", status_code=200)
def test_ai_provider(
    data: models.AIProviderTestRequest,
    requester: models.User = Depends(get_current_user),
):
    return {"data": ai_settings.test_provider(data, requester)}
