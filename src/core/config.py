from pathlib import Path
import os
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_FILE = PROJECT_ROOT / "tickets_system.db"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+pysqlite:///{DATABASE_FILE}",
)
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

DEBUG = None
LOG_LEVEL = 'INFO'

JWT_SECRET = None
JWT_ALGORITHM = None
ACCESS_TOKEN_EXPIRE_MIN = None

REDIS_URL = os.getenv("REDIS_URL")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
FRONTEND_ORIGINS = tuple(
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
)
REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS = float(
    os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS", "1")
)
REDIS_SOCKET_TIMEOUT_SECONDS = float(
    os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "1")
)
ROUTING_RECONCILIATION_BATCH_SIZE = int(
    os.getenv("ROUTING_RECONCILIATION_BATCH_SIZE", "100")
)
ROUTING_RECONCILIATION_INTERVAL_SECONDS = int(
    os.getenv("ROUTING_RECONCILIATION_INTERVAL_SECONDS", "60")
)
OVERDUE_SCAN_BATCH_SIZE = int(os.getenv("OVERDUE_SCAN_BATCH_SIZE", "100"))
OVERDUE_SCAN_INTERVAL_SECONDS = int(os.getenv("OVERDUE_SCAN_INTERVAL_SECONDS", "60"))
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 900
ANALYSIS_RATE_LIMIT_MAX_REQUESTS = 5
ANALYSIS_RATE_LIMIT_WINDOW_SECONDS = 60
ANALYZER_PROVIDER = os.getenv("ANALYZER_PROVIDER", "fake").strip().lower()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-oss-20b",
).strip()
ATTACHMENTS_DIR = Path(os.getenv("ATTACHMENTS_DIR", str(PROJECT_ROOT / "uploads")))
try:
    OPENROUTER_TIMEOUT_SECONDS = float(
        os.getenv("OPENROUTER_TIMEOUT_SECONDS", "20")
    )
except ValueError as exc:
    raise RuntimeError("OPENROUTER_TIMEOUT_SECONDS must be numeric") from exc
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
try:
    DEEPSEEK_TIMEOUT_SECONDS = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "20"))
except ValueError as exc:
    raise RuntimeError("DEEPSEEK_TIMEOUT_SECONDS must be numeric") from exc


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
    if REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS <= 0:
        raise RuntimeError("REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS must be greater than zero")
    if REDIS_SOCKET_TIMEOUT_SECONDS <= 0:
        raise RuntimeError("REDIS_SOCKET_TIMEOUT_SECONDS must be greater than zero")


def validate_routing_reconciliation_settings() -> None:
    if ROUTING_RECONCILIATION_BATCH_SIZE <= 0:
        raise RuntimeError(
            "ROUTING_RECONCILIATION_BATCH_SIZE must be greater than zero"
        )
    if ROUTING_RECONCILIATION_INTERVAL_SECONDS <= 0:
        raise RuntimeError(
            "ROUTING_RECONCILIATION_INTERVAL_SECONDS must be greater than zero"
        )
    if OVERDUE_SCAN_BATCH_SIZE <= 0:
        raise RuntimeError("OVERDUE_SCAN_BATCH_SIZE must be greater than zero")
    if OVERDUE_SCAN_INTERVAL_SECONDS <= 0:
        raise RuntimeError("OVERDUE_SCAN_INTERVAL_SECONDS must be greater than zero")


def validate_analyzer_settings() -> None:
    if ANALYZER_PROVIDER not in {"fake", "openrouter"}:
        raise RuntimeError("ANALYZER_PROVIDER must be fake or openrouter")
    if OPENROUTER_TIMEOUT_SECONDS <= 0:
        raise RuntimeError("OPENROUTER_TIMEOUT_SECONDS must be greater than zero")
    if ANALYZER_PROVIDER == "fake":
        return
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.strip():
        raise RuntimeError(
            "OPENROUTER_API_KEY is required when ANALYZER_PROVIDER=openrouter"
        )
    if not OPENROUTER_MODEL:
        raise RuntimeError(
            "OPENROUTER_MODEL is required when ANALYZER_PROVIDER=openrouter"
        )


validate_redis_settings()
validate_routing_reconciliation_settings()
