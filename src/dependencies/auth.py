from fastapi import Header, HTTPException
from src.db import operations
from src.core import security
import jwt
from src.constants import UserStatus


def get_current_user(authorization: str | None = Header(default=None)):
    
    if authorization is None or authorization.find('Bearer') == -1:
        raise HTTPException(401, detail="No authenticated")
    

    token = authorization.split('Bearer')[-1].strip()
    
    try:
        payload_data = security.decode_access_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(401, detail="Invalid credentials")
    
    if payload_data is None:
        raise HTTPException(401, detail="No logged in")
    
    # whats inside user token?

    # should i check the person who actually asks for it? what if tis an admin?
    user = operations.get_user(payload_data['sub'])   
    if user.user_status in [UserStatus.DELETED, UserStatus.BANNED]:
        raise HTTPException(403, detail="No rights")
    if user is None:
        raise HTTPException(401, detail="Requested Resourse does not exist")
    
    return user
