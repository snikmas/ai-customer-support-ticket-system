from fastapi import APIRouter, Depends

from src import models
from src.dependencies.auth import get_current_user
from src.services import analysis_results


router = APIRouter(
    prefix="/analysis-results",
    tags=["analysis-results"],
)


@router.get("/{analysis_result_id}", status_code=200)
def get_analysis_result(
    analysis_result_id: str,
    requester: models.User = Depends(get_current_user),
):
    return {
        "data": analysis_results.get_analysis_result(
            analysis_result_id,
            requester,
        )
    }
