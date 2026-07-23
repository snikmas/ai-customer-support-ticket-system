from dataclasses import dataclass

from redis import RedisError

from src.constants import logger
from src.core import (
    ANALYSIS_RATE_LIMIT_MAX_REQUESTS,
    ANALYSIS_RATE_LIMIT_WINDOW_SECONDS,
)
from src.exceptions import (
    AnalysisRateLimitExceededError,
    AnalysisRateLimitUnavailableError,
)

from .keys import build_analysis_rate_limit_key
from .redis_client import get_redis_client


ANALYSIS_RATE_LIMIT_SCRIPT_LUA = """
local requests = redis.call('INCR', KEYS[1])
if requests == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {requests, ttl}
"""


@dataclass(frozen=True)
class AnalysisRateLimitUsage:
    requests: int
    retry_after_seconds: int


def consume_analysis_creation_allowance(user_id: str) -> AnalysisRateLimitUsage:
    """Consume one allowance for a genuinely new durable analysis request."""
    try:
        client = get_redis_client()
        if client is None:
            raise AnalysisRateLimitUnavailableError()

        requests, ttl = client.eval(
            ANALYSIS_RATE_LIMIT_SCRIPT_LUA,
            1,
            build_analysis_rate_limit_key(user_id),
            ANALYSIS_RATE_LIMIT_WINDOW_SECONDS,
        )
    except RedisError as exc:
        # Do not include the Redis exception: infrastructure errors may contain
        # connection details or credentials.
        logger.warning(
            "Analysis rate limit unavailable",
            extra={"requester_id": user_id},
        )
        raise AnalysisRateLimitUnavailableError() from exc

    requests = int(requests)
    retry_after_seconds = max(1, int(ttl))
    if requests > ANALYSIS_RATE_LIMIT_MAX_REQUESTS:
        raise AnalysisRateLimitExceededError(retry_after_seconds)

    return AnalysisRateLimitUsage(
        requests=requests,
        retry_after_seconds=retry_after_seconds,
    )
