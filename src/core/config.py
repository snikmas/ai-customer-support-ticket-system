from pathlib import Path
import os
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_FILE = PROJECT_ROOT / "tickets_system.db"
DATABASE_URL = f'sqlite+pysqlite:///{DATABASE_FILE}'

DEBUG = None
LOG_LEVEL = 'INFO'

JWT_SECRET = None
JWT_ALGORITHM = None
ACCESS_TOKEN_EXPIRE_MIN = None

REDIS_URL = os.getenv("REDIS_URL")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 900


def validate_redis_settings() -> None:
    if not REDIS_ENABLED:
        return

    if not REDIS_URL or not REDIS_URL.strip():
        raise RuntimeError(
            "REDIS_ENABLED is true, but REDIS_URL is missing"
        )

    if not REDIS_URL.startswith(("redis://", "rediss://", "unix://")):
        raise RuntimeError(
            "REDIS_URL must start with redis://, rediss://, or unix://"
        )


validate_redis_settings()
