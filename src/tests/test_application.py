from fastapi.testclient import TestClient

import main


def test_health_is_healthy_when_database_and_enabled_redis_are_up(monkeypatch):
    monkeypatch.setattr(main, "REDIS_ENABLED", True)
    monkeypatch.setattr(main, "ping_database", lambda: True)
    monkeypatch.setattr(main, "ping_redis", lambda: True)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "checks": {"database": "up", "redis": "up"},
    }


def test_health_is_healthy_when_redis_is_explicitly_disabled(monkeypatch):
    monkeypatch.setattr(main, "REDIS_ENABLED", False)
    monkeypatch.setattr(main, "ping_database", lambda: True)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json()["checks"] == {
        "database": "up",
        "redis": "disabled",
    }


def test_health_is_unhealthy_when_enabled_redis_is_down(monkeypatch):
    monkeypatch.setattr(main, "REDIS_ENABLED", True)
    monkeypatch.setattr(main, "ping_database", lambda: True)
    monkeypatch.setattr(main, "ping_redis", lambda: False)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "database": "up",
        "redis": "down",
    }


def test_health_is_unhealthy_when_database_is_down(monkeypatch):
    monkeypatch.setattr(main, "REDIS_ENABLED", False)
    monkeypatch.setattr(main, "ping_database", lambda: False)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "down"


def test_lifespan_initializes_and_releases_owned_resources(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "create_db", lambda: calls.append("create_db"))
    monkeypatch.setattr(main, "initialize_redis_client", lambda: calls.append("initialize_redis"))
    monkeypatch.setattr(main, "close_redis_client", lambda: calls.append("close_redis"))
    monkeypatch.setattr(main.engine, "dispose", lambda: calls.append("dispose_database"))
    monkeypatch.setattr(main, "ping_database", lambda: True)
    monkeypatch.setattr(main, "REDIS_ENABLED", False)

    with TestClient(main.app):
        assert calls == ["create_db", "initialize_redis"]

    assert calls == [
        "create_db",
        "initialize_redis",
        "close_redis",
        "dispose_database",
    ]
