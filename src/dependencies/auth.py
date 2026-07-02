from fastapi import Header, HTTPException
from src.db import operations
from src.core import security
import jwt

#   1. Read Authorization header
#   2. Extract Bearer token
#   3. Decode/verify JWT using public key
#   4. Get user id from sub
#   5. Load user from DB
#   6. Return current user
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

    user = operations.get_user(payload_data['sub'])    
    if user is None:
        raise HTTPException(401, detail="Requested Resourse does not exist")
    
    return user
