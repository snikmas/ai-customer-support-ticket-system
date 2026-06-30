from fastapi import APIRouter, HTTPException
from datetime import datetime
from src import models, db, constants
from src.services import users as s_users, tickets as s_tickets

router = APIRouter(
    prefix='/users',
    tags=["users"]
)


# later rewrite/add: Depends(get current_user)
@router.get("/", status_code=200)
async def get_users(requester: models.User):
    res = s_users.get_all_users(requester)

    if res is None:
        return {"res": "No users"}
    else:
        return {"res": res}
        


@router.get("/{id}", status_code=200)
async def get_user(id: str, requester: models.User):
    requester_user = None #later implement
    res = s_users.get_user(id, requester_user)

    if res is None:
        return {"res": "No results"}
    return {"res": res}


@router.post("/", status_code=201)
async def create_user(cur_user: models.UserCreate, requester_user: models.User):
    user = s_users.create_user(cur_user, requester_user)
    if user is None:
        return {"res": "No results"}

    return {"res": user}

@router.patch("/{updated_user_id}", status_code=200)
async def update_user(updated_user_id: str, updated_info: models.UserUpdate, requester_user: models.User):

    res = s_users.update_user(updated_user_id, updated_info, requester_user)

    if res is None:
        return {"res": "No results"}
    
    return {'res': "the User was updated successfully\n"}
    
    # if not updated_info:
        # raise HTTPException(400, detail="No fields to update")
    
    # affected_row = db.update_user(id, updated_info)
    # if (affected_row == 0):
        # raise HTTPException(400, detail="Error during updating")


@router.delete("/{id}", status_code=200)
async def delete_user(id: str, requester_user: models.User):
    # we can frisly check if a ticket exist and later delete it? or check it using delete?
    res = s_users.delete_user(id, requester_user)

    if res is None:
        return {"res": "No results"}
    
    return {'res': "the User was deleted successfully\n"}
    
    # if affected_rows == 0:
        # raise HTTPException(404, detail="No affected rows")
    # return {"res": "The user was deleted successfully"}


@router.delete("/", status_code=200)
async def delete_all_users(requester_user: models.User):

    res = s_users.delete_all_users(requester_user)
    
    if res is None:
        return {"res": "No results"}
    
    return {'res': "Users were deleted successfully\n"}
    
