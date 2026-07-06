from src.models import LoginRequest, TokenResponse, User, RefreshSession, CreatedRefreshSession, Event
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
    
    if user.user_status != constants.UserStatus.ACTIVE:
        return None #no banned/deleted. later add another endpoint for them

    # check apssword
    validate_user = verify_password(password, user.password)

    if validate_user:
        return user
    return None

def logout_user(identifier: str) -> User | None:

    if '@' in identifier: #its an email
        user = operations.get_user_by_email(identifier)
    else:
        user = operations.get_user_by_nickname(identifier)
    if user is None:
        return  None
    
    operations.revoke_refresh_session()


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

        event = Event(
            id=constants.generate_id(),
            entity_type=constants.EntityType.TICKET,
            entity_id=refresh_session.id,
            actor_user_id=user_id.id,
            event_type=constants.EventType.REFRESH_SESSION_CREATED,
            old_value=None,
            new_value=constants._audit_json(refresh_session),
            metadata=None,
            created_at=now
        )
        res = operations.create_event(event)
        if res is False: return None
        
        return created_session #return to client a raw thing
    return None


def verify_refresh_session(raw_refresh_token: str) -> RefreshSession | None:
    # get a session -
    try:
        refresh_hash_token = hash_token(raw_refresh_token)
        if refresh_hash_token is None: return None
        
        session = operations.get_refresh_session_by_hash_refresh_token(refresh_hash_token)
        # check if user exist?
        if session and session.revoked_at is None and session.expires_at > datetime.now():
            return session #even if its none, its ok
        return None

    except RuntimeError:
        return None
    
def rotate_refresh_session(cur_session: RefreshSession) -> TokenResponse | None:
    new_raw_refresh_token = generate_refresh_token()
    now = datetime.now()

    user = operations.get_user(cur_session.user_id)
    if user is None: return None
    if user.user_status != constants.UserStatus.ACTIVE:
        return None 
    
    new_access_token = create_access_token(user)
    
    updated_session = operations.rotate_refresh_session(
        cur_session.id,
        revoked_at=None,
        expires_at=now + timedelta(weeks=1),
        hash_ref_token=hash_token(new_raw_refresh_token),
        created_at=now
        )

    event = Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=cur_session.id,
        actor_user_id=user.id,
        event_type=constants.EventType.REFRESH_SESSION_ROTATED,
        old_value=None,
        new_value=constants._audit_json(updated_session),
        metadata=None,
        created_at=now
    )
    res = operations.create_event(event)
    if res is False: return None
        
    
    
    if updated_session: 
        return TokenResponse(access_token=new_access_token, refresh_token=new_raw_refresh_token)
    return None


