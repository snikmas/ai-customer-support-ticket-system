from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.routers import analysis, users, tickets, auth, jobs, routing_catalogs
from src.cache import close_redis_client, initialize_redis_client, ping_redis
from src.core import REDIS_ENABLED, setup_logging
from src.constants import logger
from src.db.engine import engine
from src.db.utils import create_db, ping_database
from src.exceptions.domain import AppException


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    create_db()
    initialize_redis_client()
    logger.info(
        "Application resources initialized",
        extra={
            "database_available": ping_database(),
            "redis_enabled": REDIS_ENABLED,
            "redis_available": ping_redis() if REDIS_ENABLED else False,
        },
    )
    try:
        yield
    finally:
        close_redis_client()
        engine.dispose()
        logger.info("Application resources released")


app = FastAPI(lifespan=lifespan)


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
        headers=exc.headers,
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


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception):
    logger.exception(
        "Unhandled request error",
        extra={"method": request.method, "path": request.url.path},
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "Internal server error",
            }
        },
    )

app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(routing_catalogs.departments_router)
app.include_router(routing_catalogs.skills_router)
app.include_router(analysis.router)

@app.get("/")
async def root():
    return {"data": {"service": "ticket-system-api"}}


@app.get("/health")
def health():
    database_available = ping_database()
    redis_available = ping_redis() if REDIS_ENABLED else False
    healthy = database_available and (not REDIS_ENABLED or redis_available)

    content = {
        "status": "healthy" if healthy else "unhealthy",
        "checks": {
            "database": "up" if database_available else "down",
            "redis": (
                "up"
                if redis_available
                else "disabled"
                if not REDIS_ENABLED
                else "down"
            ),
        },
    }
    return JSONResponse(status_code=200 if healthy else 503, content=content)
