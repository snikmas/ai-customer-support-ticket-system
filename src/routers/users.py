from fastapi import APIRouter, HTTPException
from datetime import datetime
from src import models, db, constants
from src.services import users as s_users, tickets as s_tickets

router = APIRouter(
    prefix='/users',
    tags=["users"]
)

@router.get("/{id}", status_code=200)
async def get_user(id: str, requester: models.User):
    try:
        data = s_users.get_user(id, requester)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")

    if data is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"data": data}


# later rewrite/add: Depends(get current_user)
@router.get("/", status_code=200)
async def get_users(requester: models.User):

    try:
        data = s_users.get_all_users(requester)
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")

    if data is None:
        return {"data": []}
    else:
        return {"data": data}

@router.post("/", status_code=201)
async def create_user(cur_user: models.UserCreate, requester: models.User):

    try:
        user = s_users.create_user(cur_user, requester)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")
    
    if user is None:
        raise HTTPException(status_code=400, detail="Some error happened")

    return {"data": user}

@router.patch("/{updated_user_id}", status_code=200)
async def update_user(updated_user_id: str, updated_info: models.UserUpdate, requester: models.User):

    try:
        data = s_users.update_user(updated_user_id, updated_info, requester)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")

    if data is None:
        raise HTTPException(404, detail="Some error happened")
    
    return {'data': data}



@router.delete("/{id}", status_code=204)
async def delete_user(id: str, requester: models.User):
    try:
        data = s_users.delete_user(id, requester)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")





@router.delete("/", status_code=200)
async def delete_all_users(requester: models.User):
    try:
        data = s_users.delete_all_users(requester)
    except ValueError:
        raise HTTPException(404, detail="Value Error")
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")
    return {"data": f"Deleted: {data}"}
    
