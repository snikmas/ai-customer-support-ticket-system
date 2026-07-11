#RATE_LIMIT: RATE-LIMIT LOGIC ONLY
from . import build_login_attempt_key, get_redis_client
from src.core.config import LOGIN_RATE_LIMIT_WINDOW_SECONDS, LOGIN_RATE_LIMIT_MAX_ATTEMPTS
from src.constants import logger
from redis import RedisError


def record_failed_login(identifier: str) -> int | None:
    try:
        client = get_redis_client()
        if client is None: return None

        key = build_login_attempt_key(identifier)
        attempts = client.incr(key)

        if attempts == 1:
            client.expire(key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    except RedisError:
        logger.exception("Redis unavailable while recording a failed login")
        return None

    return attempts


def is_login_limited(identifier: str) -> bool:
    try:
        client = get_redis_client()
        if client is None: return False

        key = build_login_attempt_key(identifier)
        attempts = client.get(key)
    except RedisError:
        logger.exception("Redis unavailable while checking the login rate limit")
        return False

    if attempts is None: return False
    return int(attempts) >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS


def clear_login_attempts(identifier: str) -> bool:
    try:
        client = get_redis_client()
        if client is None: return False
        key = build_login_attempt_key(identifier)
        deleted_count = client.delete(key)
    except RedisError:
        logger.exception("Redis unavailable while clearing login attempts")
        return False

    return deleted_count > 0
