# REDIS_CLIENT: CONNECTIONS ONLY

import redis 
from src.core.config import REDIS_ENABLED, REDIS_URL


def get_redis_client():
    if not REDIS_ENABLED:
        return None
    return redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True, #give me 5 instead of b'5'
    )

def ping_redis() -> bool:
    client = get_redis_client()
    if client is None: return False

    try:
        return client.ping()
    except redis.RedisError:
        return False
    