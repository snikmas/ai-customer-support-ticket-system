#CONFIG: SETTINGS ONLY
import redis
from redis.cache import CacheConfig
import core

redis_client = redis.Redis(
    link=core.REDIS_URL,
    decode_responses=True,
    cache_config=CacheConfig(),
    )



def ping_redis() -> bool:
    return redis.ping()