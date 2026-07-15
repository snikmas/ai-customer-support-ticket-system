from fastapi import APIRouter, HTTPException, Depends, Query
from src import models, constants
from src.services import users as s_users
from src.dependencies.auth import get_current_user
from typing import Literal

router = APIRouter(
    prefix='/analysis-results',
    tags=["analysis-results"]
)

# This router intentionally uses normal `def` handlers because its SQLAlchemy
# service path is synchronous. A later end-to-end async migration would require
# AsyncSession + an async DB driver and async Redis/HTTP clients; only then
# should these handlers become `async def` and await those operations.


@router.get("/{analysis_result_id}", status_code=200)
def get_user(analysis_result_id: str, requester = Depends(get_current_user)) -> models.AnalysisResult | None:
    pass
