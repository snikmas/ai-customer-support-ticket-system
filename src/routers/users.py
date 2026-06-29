from fastapi import APIRouter, HTTPException
from datetime import datetime
from src import models, db, constants

router = APIRouter(
    prefix='/users',
    tags=["users"]
)

@router.get("/", status_code=200)
async def get_users():
    db_res = db.get_users()
    all_users = []
    if db_res:
        for row in db_res:
            all_users.append(dict(row))
        return {"res": all_users}
    else:
        return {"res": "No users"}


@router.get("/{id}", status_code=200)
async def get_user(id: str):
    db_res = db.get_user(id)
    if not db_res: 
        raise HTTPException(404, detail="No user found")
    
    user = dict(db_res)
    
    return {"res": user}


@router.post("/", status_code=201)
async def create_user(cur_user: models.UserCreate):
    # 1) generate an id 
    cur_id = constants.generate_id()

    user = models.User(id=cur_id, 
                    **cur_user.model_dump(), 
                    role=constants.Role.USER,
                    updated_at=datetime.now(), 
                    created_at=datetime.now()
                    )

    # could we always return.. rowcount? like how many rows was affected?
    db.insert_user(user.__dict__)
    return {"res": user}

@router.patch("/{id}", status_code=200)
async def update_user(id: str, new_info: models.UserUpdate):
    updated_info = new_info.model_dump(exclude_unset=True)

    if not updated_info:
        raise HTTPException(400, detail="No fields to update")
    
    affected_row = db.update_user(id, updated_info)
    if (affected_row == 0):
        raise HTTPException(400, detail="Error during updating")
    return {"res": "The User was updated successfully"}
    
@router.delete("/{id}", status_code=200)
async def delete_user(id: str):
    # we can frisly check if a ticket exist and later delete it? or check it using delete?
    affected_rows = db.delete_user(id)
    if affected_rows == 0:
        raise HTTPException(404, detail="No affected rows")
    return {"res": "The user was deleted successfully"}

@router.delete("/", status_code=200)
async def delete_all_users():
    affected_rows = db.delete_all_users()
    return {"res": f"{affected_rows} user(s) was/were deleted"}