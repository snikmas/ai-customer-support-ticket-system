from fastapi import Header, HTTPException
from src.db import operations
from src.core import security
import jwt
from src.constants import UserStatus


def get_current_user(authorization: str | None = Header(default=None)):
    
    if authorization is None:
        raise HTTPException(401, detail="No authenticated")
    
    parts = authorization.split()
    if len(parts) != 2:
        raise HTTPException(401, detail="Invalid authorization header")

    scheme = parts[0]
    token = parts[1]
    
    if scheme != "Bearer":
        raise HTTPException(401, detail="Invalid authorization scheme")
    
    try:
        payload_data = security.decode_access_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(401, detail="Invalid credentials")
    
    if payload_data is None:
        raise HTTPException(401, detail="No logged in")
    
    # whats inside user token?

    user = operations.get_user(payload_data['sub'])   
    
    if user is None:
        raise HTTPException(401, detail="Requested Resourse does not exist")

    if user.user_status in [UserStatus.DELETED, UserStatus.BANNED]:
        raise HTTPException(403, detail="No rights")
    
    
    return user
