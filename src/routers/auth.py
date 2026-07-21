from fastapi import APIRouter
from src import models
from src.core import security
from src.cache import record_failed_login, is_login_limited, clear_login_attempts
from src.services.auth import (
    create_refresh_session_for_user,
    login_user,
    logout_user,
    rotate_refresh_session,
    verify_refresh_session,
)
from datetime import datetime, timezone
from src.exceptions import (
    InternalOperationError,
    InvalidCredentialsError,
    RateLimitExceededError,
    RefreshSessionNotFoundError,
    RefreshSessionRevokedError,
)
router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)


@router.post("/login")
def login(login_request: models.LoginRequest) -> models.TokenResponse:

    if login_request.nickname is not None:
        identifier = login_request.nickname
    else:
        identifier = login_request.email

    if is_login_limited(identifier):
        raise RateLimitExceededError()

    user = login_user(identifier, login_request.password)
    
    if user is None:
        record_failed_login(identifier)
        raise InvalidCredentialsError()

    # user is ok, clear redis
    clear_login_attempts(identifier)

    raw_access_token = security.create_access_token(user)
    created_refresh_section = create_refresh_session_for_user(user.id)

    if created_refresh_section is None or raw_access_token is None:
        raise InternalOperationError("Unable to create login session", code="login_session_creation_failed")

    return models.TokenResponse(
        access_token=raw_access_token,
        refresh_token=created_refresh_section.refresh_token
    )


@router.post("/refresh")
def refresh(refresh_request: models.RefreshTokenRequest) -> models.TokenResponse:
    refresh_session = verify_refresh_session(refresh_request.refresh_token)
    token_response = rotate_refresh_session(refresh_session)
    if token_response is None:
        # A concurrent or repeated use lost the atomic token-rotation update.
        raise RefreshSessionRevokedError("Refresh session is no longer active")
    
    return token_response

@router.post("/logout")
def logout(logout_req: models.LogoutRequest):
    res = logout_user(logout_req.refresh_token)

    if res is not True:
        raise RefreshSessionNotFoundError()

    
    return {"data": {"logged_out": True}}
