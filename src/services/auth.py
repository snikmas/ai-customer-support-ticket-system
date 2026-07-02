from src.models import LoginRequest, LoginResponse, User, RefreshSession, CreatedRefreshSession
from src import constants
from src.core.security import verify_password, create_access_token, generate_refresh_token, hash_token
from .permissions import check_for_access
from src.db import operations
from src.constants.helpers import generate_id
from datetime import datetime, timedelta


def login_user(identifier: str, password: str) -> User | None:

    if '@' in identifier: #its an email
        user = operations.get_user_by_email(identifier)
    else:
        user = operations.get_user_by_nickname(identifier)
    if user is None:
        return  None
    
    # check apssword
    validate_user = verify_password(password, user.password)
    if validate_user:
        return user
    return None

# idea: one refresh session = one devcei/browser #returns refresh session id, raw
def create_refresh_session_for_user(user_id: str) -> CreatedRefreshSession | None:
    now = datetime.now()
    raw_refresh_token = generate_refresh_token()

    refresh_session = RefreshSession(
        id=generate_id(),
        user_id=user_id,
        refresh_token_hash=hash_token(raw_refresh_token), #maybe later change its name for hash_secrets 
        expires_at=now + timedelta(weeks=1),
        revoked_at=None,
        created_at=now
        )
    
    if operations.create_refresh_session(refresh_session): # is true
        created_session = CreatedRefreshSession(refresh_session_id=refresh_session.id, refresh_token=raw_refresh_token)
        return created_session #return to client a raw thing
    return None


def verify_refresh_session(session_id: str, raw_refresh_token: str) -> RefreshSession | None:
    # get a session -