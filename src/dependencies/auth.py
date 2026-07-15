from fastapi import Header, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.db import operations
from src.core import security
import jwt
from src.constants import UserStatus

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),):
    if credentials is None: raise HTTPException(401, detail="No authenticated")

    token = credentials.credentials

    try:
        payload_data = security.decode_access_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(401, detail="Invalid credentials")
    
    if payload_data is None:
        raise HTTPException(401, detail="No logged in")

    user_id = payload_data.get("sub")
    if not isinstance(user_id, str) or not user_id or payload_data.get("type") != "access":
        raise HTTPException(401, detail="Invalid credentials")

    user = operations.get_user(user_id)
    
    if user is None:
        raise HTTPException(401, detail="Requested Resourse does not exist")

    if user.user_status in [UserStatus.DELETED, UserStatus.BANNED]:
        raise HTTPException(403, detail="No rights")
        
    return user

