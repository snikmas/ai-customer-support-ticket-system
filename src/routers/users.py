from fastapi import APIRouter, HTTPException, Depends, Query
from src import models, constants
from src.services import users as s_users
from src.dependencies.auth import get_current_user
from typing import Literal

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
                    ):

    data = s_users.get_all_users(requester, limit, offset, sort_by, sort_order)
    if data:
        return {"data": [models.UserResponse.model_validate(user, from_attributes=True) for user in data]}
    return {"data": []}

@router.post("/", status_code=201)
def create_user(cur_user: models.UserCreate):
    data = s_users.create_user(cur_user)
    user = models.UserResponse.model_validate(data, from_attributes=True)
    return {"data": user}

@router.patch("/{updated_user_id}", status_code=200)
def update_user(updated_user_id: str, updated_info: models.UserUpdate, requester = Depends(get_current_user)):
    data = s_users.update_user(updated_user_id, updated_info, requester)
    user = models.UserResponse.model_validate(data, from_attributes=True)
    return {'data': user}



@router.delete("/{id}", status_code=204)
def delete_user(id: str, requester = Depends(get_current_user)):
    s_users.delete_user(id, requester)


@router.delete("/", status_code=200)
def delete_all_users(requester = Depends(get_current_user)):
    raise HTTPException(
        status_code=503,
        detail="Bulk user deletion is temporarily unavailable",
    )
    
