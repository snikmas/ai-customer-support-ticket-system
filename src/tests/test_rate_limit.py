from types import SimpleNamespace

import pytest
from redis import RedisError

from main import app
from src.cache import rate_limit
from src.exceptions import CacheUnavailableError
from src.routers import auth as auth_router


def test_rate_limit_check_is_skipped_when_redis_is_disabled(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: None)

    # Redis disabled by configuration must not make login unavailable.
    assert rate_limit.is_login_limited("mary") is False
    assert rate_limit.record_failed_login("mary") == 0
    assert rate_limit.clear_login_attempts("mary") is False


def test_rate_limit_check_translates_redis_failure(monkeypatch):
    client = SimpleNamespace(
        get=lambda _: (_ for _ in ()).throw(RedisError("unavailable"))
    )
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: client)

    with pytest.raises(CacheUnavailableError):
        rate_limit.is_login_limited("mary")


def test_login_returns_503_when_rate_limit_check_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        auth_router,
        "is_login_limited",
        lambda _: (_ for _ in ()).throw(CacheUnavailableError()),
    )

    from fastapi.testclient import TestClient

    response = TestClient(app).post(
        "/auth/login",
        json={"nickname": "mary", "password": "valid-password"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "cache_unavailable"


def test_login_returns_503_when_failed_attempt_cannot_be_recorded(monkeypatch):
    monkeypatch.setattr(auth_router, "is_login_limited", lambda _: False)
    monkeypatch.setattr(auth_router, "login_user", lambda *_: None)
    monkeypatch.setattr(
        auth_router,
        "record_failed_login",
        lambda _: (_ for _ in ()).throw(CacheUnavailableError()),
    )

    from fastapi.testclient import TestClient

    response = TestClient(app).post(
        "/auth/login",
        json={"nickname": "mary", "password": "wrong-password"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "cache_unavailable"
