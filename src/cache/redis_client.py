# REDIS_CLIENT: CONNECTIONS ONLY

import redis 
from src.core.config import (
    REDIS_ENABLED,
    REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
    REDIS_SOCKET_TIMEOUT_SECONDS,
    REDIS_URL,
)

_redis_client = None


def initialize_redis_client():
    """Create the process-wide Redis connection pool owner.

    Redis connections are lazy at the socket level, so startup may create this
    object even while Redis is down. ``ping_redis`` reports actual readiness.
    """
    global _redis_client
    if not REDIS_ENABLED:
        return None
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            REDIS_URL,
            socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
        )
    return _redis_client


def get_redis_client():
    return initialize_redis_client()


def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None

def ping_redis() -> bool:
    client = get_redis_client()
    if client is None: return False

    try:
        return client.ping()
    except redis.RedisError:
        return False
    
