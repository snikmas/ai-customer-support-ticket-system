from fastapi import APIRouter, Depends, Query
from src import models, constants
from src.services import users as s_users
from src.dependencies.auth import get_current_user
from typing import Literal
import inspect
from src.exceptions import ServiceUnavailableError

router = APIRouter(
    prefix='/users',
    tags=["users"]
)

# This router intentionally uses normal `def` handlers because its SQLAlchemy
# service path is synchronous. A later end-to-end async migration would require
# AsyncSession + an async DB driver and async Redis/HTTP clients; only then
# should these handlers become `async def` and await those operations.


@router.get("/{id}", status_code=200)
def get_user(id: str, requester = Depends(get_current_user)):
    data = s_users.get_user(id, requester)
    user = models.UserResponse.model_validate(data, from_attributes=True)
    return {"data": user}


@router.get("/", status_code=200)
def get_users(requester = Depends(get_current_user),
                    limit: int = Query(constants.DEFAULT_PAGE_LIMIT,
                                       ge=1,
                                       le=constants.MAX_PAGE_LIMIT),
                    offset: int = Query(0, ge=0),
                    sort_by: Literal[
                        'created_at', 
                        'user_status', 
                        'role', 
                        'first_name', 
                        'last_name'] = constants.DEFAULT_SORT_BY,
                    sort_order: Literal['asc', 'desc'] = constants.DEFAULT_SORT_ORDER,
                    role: constants.Role | None = None,
                    user_status: constants.UserStatus | None = None,
                    search: str | None = Query(None, max_length=200),
                    ):

    service_parameters = inspect.signature(s_users.get_all_users).parameters
    supports_filters = (
        "role" in service_parameters
        or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in service_parameters.values())
    )
    if supports_filters:
        data = s_users.get_all_users(
            requester,
            limit,
            offset,
            sort_by,
            sort_order,
            role=role,
            user_status=user_status,
            search=search,
        )
    else:
        data = s_users.get_all_users(requester, limit, offset, sort_by, sort_order)
    if data:
        return {"data": [models.UserResponse.model_validate(user, from_attributes=True) for user in data]}
    return {"data": []}

@router.post("/", status_code=201)
def create_user(cur_user: models.UserCreate):
    data = s_users.create_user(cur_user)
    user = models.UserResponse.model_validate(data, from_attributes=True)
    return {"data": user}


@router.post("/staff", status_code=201)
def create_staff_user(
    data: models.StaffCreate,
    requester=Depends(get_current_user),
):
    user = s_users.create_staff_user(data, requester)
    return {"data": models.UserResponse.model_validate(user, from_attributes=True)}

@router.patch("/{updated_user_id}", status_code=200)
def update_user(updated_user_id: str, updated_info: models.UserUpdate, requester = Depends(get_current_user)):
    data = s_users.update_user(updated_user_id, updated_info, requester)
    user = models.UserResponse.model_validate(data, from_attributes=True)
    return {'data': user}


@router.patch("/{agent_id}/availability", status_code=200)
def update_agent_availability(
    agent_id: str,
    update_data: models.AgentAvailabilityUpdate,
    requester=Depends(get_current_user),
):
    profile = s_users.update_agent_availability(agent_id, update_data, requester)
    return {"data": profile}


@router.get("/{agent_id}/agent-profile", status_code=200)
def get_agent_profile(
    agent_id: str,
    requester=Depends(get_current_user),
):
    return {"data": s_users.get_agent_profile_settings(agent_id, requester)}


@router.patch("/{agent_id}/agent-profile", status_code=200)
def update_agent_profile_settings(
    agent_id: str,
    update_data: models.AgentProfileManagementUpdate,
    requester=Depends(get_current_user),
):
    profile = s_users.update_agent_profile_settings(agent_id, update_data, requester)
    return {"data": profile}



@router.delete("/{id}", status_code=204)
def delete_user(id: str, requester = Depends(get_current_user)):
    s_users.delete_user(id, requester)


@router.delete("/", status_code=200)
def delete_all_users(requester = Depends(get_current_user)):
    raise ServiceUnavailableError(
        "Bulk user deletion is temporarily unavailable",
        code="bulk_user_deletion_unavailable",
    )
    
