from fastapi import APIRouter, HTTPException, Depends
from src import models, db, constants
from src.services import *
from src.dependencies import *

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

@router.post("/login")
def login(login_request: models.LoginRequest) -> models.LoginResponse:
    user = None
    if login_request.nickname is not None:
        user = login_user(login_request.nickname, login_request.password)
    elif login_request.email is not None:
        user = login_user(login_request.email, login_request.password)
    else:
        return None
    
    if user is None:
        raise HTTPException(401, detail="Ivalid credentials")
    
    # put only user.id cuz its not encrupted
    access_token = create_access_token(user)
    if access_token is None:
        raise HTTPException(400, status_code="Something went wrong")

    return models.LoginResponse(
        access_token=access_token,
    )