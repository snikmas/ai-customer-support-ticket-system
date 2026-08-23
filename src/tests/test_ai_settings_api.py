from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import app
from src import constants, models
from src.dependencies.auth import get_current_user
from src.services import ai_settings


def teardown_function():
    app.dependency_overrides.clear()


def test_manager_cannot_read_ai_settings():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="manager-1",
        role=constants.Role.MANAGER,
    )
    response = TestClient(app).get("/ai-settings/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ai_settings_forbidden"


def test_admin_route_returns_safe_settings_shape(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="admin-1",
        role=constants.Role.ADMIN,
    )
    expected = models.AISettingsResponse(
        provider="fake",
        model="deterministic-fake-v1",
        version=1,
        updated_at=datetime.now(timezone.utc),
        updated_by_user_id=None,
        providers=[models.ProviderCapability(
            provider="fake",
            configured=True,
            configuration_status="ready",
            selectable_models=["deterministic-fake-v1"],
            default_model="deterministic-fake-v1",
            privacy_notice="local",
        )],
    )
    monkeypatch.setattr(ai_settings, "get_settings", lambda _: expected)

    response = TestClient(app).get("/ai-settings/")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["provider"] == "fake"
    assert "api_key" not in str(body).lower()
