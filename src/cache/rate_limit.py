#RATE_LIMIT: RATE-LIMIT LOGIC ONLY
from . import build_login_attempt_key, get_redis_client
from src.core.config import LOGIN_RATE_LIMIT_WINDOW_SECONDS, LOGIN_RATE_LIMIT_MAX_ATTEMPTS

def record_failed_login(identifier: str) -> int | None:
    client = get_redis_client()
    if client is None: return None

    key = build_login_attempt_key(identifier)
    attempts = client.incr(key)

    if attempts == 1:
        client.expire(key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)

    return attempts

def is_login_limited(identifier: str) -> bool:
    client = get_redis_client()
    if client is None: return False

    key = build_login_attempt_key(identifier)
    attempts = client.get(key)

    if attempts is None: return False
    return int(attempts) >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS

def clear_login_attempts(identifier: str) -> bool:
    client = get_redis_client()
    if client is None: return False

    key = build_login_attempt_key(identifier)
    deleted_count = client.delete(key)

    return deleted_count > 0
