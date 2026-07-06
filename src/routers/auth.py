from fastapi import APIRouter, HTTPException, Depends
from src import models, db, constants
from src.services import *
from src.dependencies import *
from datetime import datetime, timezone
router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)


@router.post("/login")
def login(login_request: models.LoginRequest) -> models.TokenResponse:
    user = None
    if login_request.nickname is not None:
        user = login_user(login_request.nickname, login_request.password)
    elif login_request.email is not None:
        user = login_user(login_request.email, login_request.password)
    else:
        return None
    
    if user is None:
        raise HTTPException(401, detail="Ivalid credentials")


    raw_access_token = security.create_access_token(user)
    created_refresh_section = create_refresh_session_for_user(user.id)

    if created_refresh_section is None or raw_access_token is None:
        raise HTTPException(400, detail="Something went wrong")

    return models.TokenResponse(
        access_token=raw_access_token,
        refresh_token=created_refresh_section.refresh_token
    )


@router.post("/refresh")
def refresh(refresh_request: models.RefreshTokenRequest) -> models.TokenResponse:
    if refresh_request.refresh_token is None:
        raise HTTPException(400, "No data")

    try: 
        refresh_session = verify_refresh_session(refresh_request.refresh_token)
        if refresh_session is None:
            raise HTTPException(401, detail="Invalid credentials")
        
        token_response = rotate_refresh_session(refresh_session)
        if token_response is None:
            raise HTTPException(400, detail="The token not found")

    except RuntimeError:
        raise HTTPException(400, detail="Some runtime error. Try later")
    
    return token_response

@router.post("/logout")
def logout(logout_req: models.LogoutRequest):
    if logout_req.refresh_token is None:
        raise HTTPException(400, "No Data")

    res = logout_user(logout_req.refresh_token)

    if res is not True:
        raise HTTPException(400, detail="Sometihng went wrong")

    
    return {"Data": "Bye!"}
