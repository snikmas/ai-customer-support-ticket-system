from src.models import LoginRequest, TokenResponse, User, RefreshSession, CreatedRefreshSession, Event
from src import constants
from src.core.security import hash_password, password_needs_rehash, verify_password, create_access_token, generate_refresh_token, hash_token
from .permissions import check_for_access
from src.db import operations
from src.constants.helpers import generate_id
from datetime import datetime, timedelta, timezone
from src.exceptions import (
    InternalOperationError,
    RefreshSessionExpiredError,
    RefreshSessionNotFoundError,
    RefreshSessionRevokedError,
)


def _refresh_session_audit_data(refresh_session) -> dict:
    return {
        "id": refresh_session.id,
        "user_id": refresh_session.user_id,
        "expires_at": refresh_session.expires_at,
        "revoked_at": refresh_session.revoked_at,
        "created_at": refresh_session.created_at,
    }


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
        if password_needs_rehash(user.password):
            upgraded_user = operations.update_user(
                user.id,
                {
                    "password": hash_password(password),
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            if upgraded_user is not None:
                user = upgraded_user
        return user
    return None

def logout_user(refresh_token_raw: str) -> bool:

    # 1. get session
    hashed_token = hash_token(refresh_token_raw)
    session = operations.get_refresh_session_by_hash_refresh_token(hashed_token)
    if session is None: return False

    if session.revoked_at is not None:
        return False
    if session.expires_at < datetime.now(timezone.utc):
        return False
    
    now = datetime.now(timezone.utc)
    event = Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.REFRESH_SESSION,
        entity_id=session.id,
        actor_user_id=session.user_id,
        event_type=constants.EventType.REFRESH_SESSION_REVOKED,
        old_value=constants._audit_json({"revoked_at": session.revoked_at}),
        new_value=constants._audit_json({"revoked_at": now}),
        metadata=None,
        created_at=now
    )

    return operations.revoke_refresh_session(session.id, now, event)


def create_refresh_session_for_user(user_id: str) -> CreatedRefreshSession | None:
    now = datetime.now(timezone.utc)
    raw_refresh_token = generate_refresh_token()

    refresh_session = RefreshSession(
        id=generate_id(),
        user_id=user_id,
        refresh_token_hash=hash_token(raw_refresh_token),
        expires_at=now + timedelta(weeks=1),
        revoked_at=None,
        created_at=now
        )
    
    event = Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.REFRESH_SESSION,
        entity_id=refresh_session.id,
        actor_user_id=user_id,
        event_type=constants.EventType.REFRESH_SESSION_CREATED,
        old_value=None,
        new_value=constants._audit_json(_refresh_session_audit_data(refresh_session)),
        metadata=None,
        created_at=now
    )

    if operations.create_refresh_session(refresh_session, event):
        created_session = CreatedRefreshSession(refresh_session_id=refresh_session.id, refresh_token=raw_refresh_token)
        return created_session #return to client a raw thing
    return None


def verify_refresh_session(raw_refresh_token: str) -> RefreshSession | None:
    try:
        refresh_hash_token = hash_token(raw_refresh_token)
    except RuntimeError as exc:
        raise InternalOperationError(
            "Token service is unavailable",
            code="token_service_unavailable",
        ) from exc

    session = operations.get_refresh_session_by_hash_refresh_token(refresh_hash_token)
    if session is None:
        raise RefreshSessionNotFoundError()
    if session.revoked_at is not None:
        raise RefreshSessionRevokedError()
    if session.expires_at <= datetime.now(timezone.utc):
        raise RefreshSessionExpiredError()
    return session
    
def rotate_refresh_session(cur_session: RefreshSession) -> TokenResponse | None:
    new_raw_refresh_token = generate_refresh_token()
    now = datetime.now(timezone.utc)

    user = operations.get_user(cur_session.user_id)
    if user is None: return None
    if user.user_status != constants.UserStatus.ACTIVE:
        return None 
    
    new_access_token = create_access_token(user)
    
    new_expires_at = now + timedelta(weeks=1)
    new_refresh_token_hash = hash_token(new_raw_refresh_token)
    event = Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.REFRESH_SESSION,
        entity_id=cur_session.id,
        actor_user_id=user.id,
        event_type=constants.EventType.REFRESH_SESSION_ROTATED,
        old_value=None,
        new_value=constants._audit_json({
            "id": cur_session.id,
            "user_id": cur_session.user_id,
            "expires_at": new_expires_at,
            "revoked_at": None,
            "created_at": now,
        }),
        metadata=None,
        created_at=now
    )

    updated_session = operations.rotate_refresh_session(
        cur_session.id,
        current_hash=cur_session.refresh_token_hash,
        revoked_at=None,
        expires_at=new_expires_at,
        hash_ref_token=new_refresh_token_hash,
        created_at=now,
        event_data=event,
        )
    if updated_session is None:
        return None
        
    return TokenResponse(access_token=new_access_token, refresh_token=new_raw_refresh_token)
