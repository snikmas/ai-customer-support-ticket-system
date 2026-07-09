from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime
from src import models, db, constants
from src.services import users as s_users
from src.dependencies.auth import get_current_user
from typing import Literal

router = APIRouter(
    prefix='/users',
    tags=["users"]
)


@router.get("/{id}", status_code=200)
async def get_user(id: str, requester = Depends(get_current_user)):
    try:
        data = s_users.get_user(id, requester)
        if data:
            user = models.UserResponse.model_validate(data, from_attributes=True)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")

    if data is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"data": user}


@router.get("/", status_code=200)
async def get_users(requester = Depends(get_current_user),
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

    try:
        data = s_users.get_all_users(requester, limit, offset, sort_by, sort_order)
        if data:
            return {"data": [models.UserResponse.model_validate(user, from_attributes=True) for user in data]}
        else:
            return {"data": []}
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")

@router.post("/", status_code=201)
async def create_user(cur_user: models.UserCreate):

    try:
        data = s_users.create_user(cur_user)
        if data:
            user = models.UserResponse.model_validate(data, from_attributes=True)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")
    
    if data is None:
        raise HTTPException(status_code=400, detail="Some error happened")

    return {"data": user}

@router.patch("/{updated_user_id}", status_code=200)
async def update_user(updated_user_id: str, updated_info: models.UserUpdate, requester = Depends(get_current_user)):

    try:
        data = s_users.update_user(updated_user_id, updated_info, requester)
        if data:
            user = models.UserResponse.model_validate(data, from_attributes=True)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")

    if data is None:
        raise HTTPException(404, detail="Some error happened")
    
    return {'data': user}



@router.delete("/{id}", status_code=204)
async def delete_user(id: str, requester = Depends(get_current_user)):
    try:
        s_users.delete_user(id, requester)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")


@router.delete("/", status_code=200)
async def delete_all_users(requester = Depends(get_current_user)):
    try:
        data = s_users.delete_all_users(requester)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")
    return {"data": f"Deleted: {data}"}
    
