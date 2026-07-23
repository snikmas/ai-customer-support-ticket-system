from types import SimpleNamespace

import pytest
from redis import RedisError

from main import app
from src.cache import analysis_rate_limit
from src.cache.keys import build_analysis_rate_limit_key
from src.exceptions import (
    AnalysisRateLimitExceededError,
    AnalysisRateLimitUnavailableError,
)


class ScriptedRedis:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def eval(self, script, key_count, key, window_seconds):
        self.calls.append((script, key_count, key, window_seconds))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_analysis_rate_limit_key_is_dedicated_and_user_scoped():
    assert build_analysis_rate_limit_key(" User-1 ") == "analysis_rate_limit:user:user-1"


def test_first_five_new_analysis_requests_are_allowed(monkeypatch):
    client = ScriptedRedis([(request_number, 60) for request_number in range(1, 6)])
    monkeypatch.setattr(analysis_rate_limit, "get_redis_client", lambda: client)

    usages = [
        analysis_rate_limit.consume_analysis_creation_allowance("user-1")
        for _ in range(5)
    ]

    assert [usage.requests for usage in usages] == [1, 2, 3, 4, 5]
    assert all(call[2] == "analysis_rate_limit:user:user-1" for call in client.calls)
    assert all(call[3] == 60 for call in client.calls)


def test_sixth_analysis_request_is_limited_with_retry_after(monkeypatch):
    client = ScriptedRedis([(6, 37)])
    monkeypatch.setattr(analysis_rate_limit, "get_redis_client", lambda: client)

    with pytest.raises(AnalysisRateLimitExceededError) as raised:
        analysis_rate_limit.consume_analysis_creation_allowance("user-1")

    assert raised.value.retry_after_seconds == 37
    assert raised.value.headers == {"Retry-After": "37"}


def test_expired_window_starts_again_at_one(monkeypatch):
    client = ScriptedRedis([(6, 1), (1, 60)])
    monkeypatch.setattr(analysis_rate_limit, "get_redis_client", lambda: client)

    with pytest.raises(AnalysisRateLimitExceededError):
        analysis_rate_limit.consume_analysis_creation_allowance("user-1")

    usage = analysis_rate_limit.consume_analysis_creation_allowance("user-1")
    assert usage.requests == 1
    assert usage.retry_after_seconds == 60


def test_analysis_limit_is_isolated_by_user(monkeypatch):
    client = ScriptedRedis([(5, 20), (1, 60)])
    monkeypatch.setattr(analysis_rate_limit, "get_redis_client", lambda: client)

    analysis_rate_limit.consume_analysis_creation_allowance("user-1")
    analysis_rate_limit.consume_analysis_creation_allowance("user-2")

    assert client.calls[0][2] == "analysis_rate_limit:user:user-1"
    assert client.calls[1][2] == "analysis_rate_limit:user:user-2"


def test_analysis_limit_fails_closed_when_redis_is_disabled(monkeypatch):
    monkeypatch.setattr(analysis_rate_limit, "get_redis_client", lambda: None)

    with pytest.raises(AnalysisRateLimitUnavailableError):
        analysis_rate_limit.consume_analysis_creation_allowance("user-1")


def test_analysis_limit_hides_redis_failure_details(monkeypatch, caplog):
    secret = "redis://user:secret-password@example.invalid"
    client = ScriptedRedis([RedisError(secret)])
    monkeypatch.setattr(analysis_rate_limit, "get_redis_client", lambda: client)
    caplog.set_level("WARNING")

    with pytest.raises(AnalysisRateLimitUnavailableError) as raised:
        analysis_rate_limit.consume_analysis_creation_allowance("user-1")

    assert secret not in caplog.text
    assert secret not in raised.value.message


def test_analysis_rate_limit_error_handler_returns_429_and_header():
    from fastapi.testclient import TestClient

    @app.get("/_test/analysis-rate-limit")
    def limited_route():
        raise AnalysisRateLimitExceededError(23)

    response = TestClient(app).get("/_test/analysis-rate-limit")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "23"
    assert response.json() == {
        "error": {
            "code": "analysis_rate_limit_exceeded",
            "message": "Too many analysis requests",
        }
    }
