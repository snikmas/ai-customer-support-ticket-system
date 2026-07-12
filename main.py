from fastapi import FastAPI, APIRouter, Request
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from src.constants import helpers
from src.routers import users, tickets, auth
from src.db.utils import create_db
from src.core import setup_logging
from src.exceptions.domain import AppException

# later convert to startup/lifespan
create_db()
setup_logging()


#i guess.. we should put all configuration to the oncfig file later

app = FastAPI()


@app.exception_handler(AppException)
async def handle_app_exception(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"http_{exc.status_code}",
                "message": str(exc.detail),
            }
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Invalid request data",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )

app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(auth.router)

@app.get("/")
async def root():
    return {"res": "hiiii"}
