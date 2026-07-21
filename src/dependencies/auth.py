from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.db import operations
from src.core import security
import jwt
from src.constants import UserStatus
from src.exceptions import AuthenticationError, InactiveUserError, InvalidCredentialsError

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),):
    if credentials is None:
        raise AuthenticationError()

    # Accepting a string here keeps direct unit tests simple; requests receive
    # HTTPAuthorizationCredentials from HTTPBearer.
    if isinstance(credentials, str):
        scheme, separator, token = credentials.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            raise AuthenticationError()
    else:
        token = credentials.credentials

    try:
        payload_data = security.decode_access_token(token)
    except jwt.InvalidTokenError:
        raise InvalidCredentialsError()
    
    if payload_data is None:
        raise InvalidCredentialsError()

    user_id = payload_data.get("sub")
    if not isinstance(user_id, str) or not user_id or payload_data.get("type") != "access":
        raise InvalidCredentialsError()

    user = operations.get_user(user_id)
    
    if user is None:
        raise InvalidCredentialsError()

    if user.user_status in [UserStatus.DELETED, UserStatus.BANNED]:
        raise InactiveUserError()
        
    return user
