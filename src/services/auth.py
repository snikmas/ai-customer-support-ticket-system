from src.models import LoginRequest, TokenResponse, User, RefreshSession, CreatedRefreshSession
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


def verify_refresh_session(raw_refresh_token: str) -> RefreshSession | None:
    # get a session -
    try:
        refresh_hash_token = hash_token(raw_refresh_token)
        
        session = operations.get_refresh_session_by_hash_refresh_token(refresh_hash_token)
        return session #even if its none, its ok

    except RuntimeError:
        # what to do here in this case?
        return None
    
def rotate_refresh_session(cur_session: RefreshSession) -> TokenResponse | None:
    new_raw_refresh_token = generate_refresh_token()
    now = datetime.now()

    
        # have to: update the refresh session
        # update the access token
        # so 1. create a new access token using user id (find user id)
        # 2. create a new access token
        # update the refresh seesssion

    user = operations.get_user(cur_session.user_id)
    new_access_token = create_access_token(user)
    
    updated_session = operations.rotate_refresh_session(
        cur_session.id,
        revoked_at=now,
        expires_at=now + timedelta(weeks=1),
        hash_ref_token=hash_token(new_raw_refresh_token))
    
    if updated_session: 
        return TokenResponse(access_token=new_access_token, refresh_token=new_raw_refresh_token)
    return None


