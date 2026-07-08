from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DATABASE_FILE = PROJECT_ROOT / "tickets_system.db"
DATABASE_URL = f'sqlite+pysqlite:///{DATABASE_FILE}'

DEBUG = None
LOG_LEVEL = 'INFO'

JWT_SECRET = None
JWT_ALGORITHM = None
ACCESS_TOKEN_EXPIRE_MIN = None

REDIS_URL = os.getenv("REDIS_URL")
REDIS_ENABLED = True
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 900