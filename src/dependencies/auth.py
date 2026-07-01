from fastapi import Header, HTTPException
from src.db import operations

def get_current_user(x_user_id: str | None = Header(default=None)):
    if x_user_id is None:
        raise HTTPException(401, detail="No logged in")
    
    user = operations.get_user(x_user_id)    
    if user is None:
        raise HTTPException(401, detail="Requested Resourse does not exist")
    
    return user

