#RATE_LIMIT: RATE-LIMIT LOGIC ONLY
from . import build_login_attempt_key, get_redis_client
from src.core.config import LOGIN_RATE_LIMIT_WINDOW_SECONDS, LOGIN_RATE_LIMIT_MAX_ATTEMPTS
from src.constants import logger
from src.exceptions import CacheUnavailableError
from redis import RedisError

RATE_LIMIT_INCREMENT_SCRIPT_LUA = '''
            local attempts = redis.call('INCR', KEYS[1])
            if attempts == 1 then 
                redis.call('EXPIRE', KEYS[1], ARGV[1])
            end
            return attempts
        '''

def record_failed_login(identifier: str) -> int:
    try:
        client = get_redis_client()
        if client is None:
            raise CacheUnavailableError()
        key = build_login_attempt_key(identifier)

        # the problem with this code: it can run client.incr but git an error in client.expire. result: a key without ttl -> a user could be permamently blocked
        # this is a redis feature, that's why
        # attempts = client.incr(key)
        # if attempts == 1:
            # client.expire(key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)


        # solution.. lua? cuz it runs everything in a single redis operation
        # okay, just checked some videos. next goal: learn lua
        # what a beauty langauge: arrays/etc starts from 1 and not 0, okay
        attempts = client.eval(
            RATE_LIMIT_INCREMENT_SCRIPT_LUA, 
            1, 
            key, 
            LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        return attempts

    except RedisError as exc:
        logger.exception("Redis unavailable while recording a failed login")
        raise CacheUnavailableError() from exc



def is_login_limited(identifier: str) -> bool:
    try:
        client = get_redis_client()
        if client is None:
            raise CacheUnavailableError()

        key = build_login_attempt_key(identifier)
        attempts = client.get(key)
    except RedisError as exc:
        logger.exception("Redis unavailable while checking the login rate limit")
        raise CacheUnavailableError() from exc

    if attempts is None: return False
    return int(attempts) >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS


def clear_login_attempts(identifier: str) -> bool:
    try:
        client = get_redis_client()
        if client is None:
            raise CacheUnavailableError()
        key = build_login_attempt_key(identifier)
        deleted_count = client.delete(key)
    except RedisError as exc:
        logger.exception("Redis unavailable while clearing login attempts")
        raise CacheUnavailableError() from exc

    return deleted_count > 0
