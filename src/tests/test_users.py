from fastapi.testclient import TestClient

from main import app
from src import constants
from src.routers import users as users_router


client = TestClient(app)


def test_get_users_requires_authentication():
    response = client.get("/users/")

    assert response.status_code == 401


def test_get_users_returns_current_service_shape(monkeypatch, make_user):
    requester = make_user(role=constants.Role.MANAGER)
    returned_user = make_user(id="visible-user", nickname="visible")

    app.dependency_overrides[users_router.get_current_user] = lambda: requester
    monkeypatch.setattr(
        users_router.s_users,
        "get_all_users",
        lambda current_user: [returned_user] if current_user is requester else [],
    )

    response = client.get("/users/")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "data" in body
    assert body["data"][0]["id"] == "visible-user"
    assert "password" not in body["data"][0]


def test_create_user_requires_password_and_returns_public_user(monkeypatch, make_user):
    created_user = make_user(id="created-user", nickname="new-user")
    captured = {}

    def fake_create_user(user_create):
        captured["password"] = user_create.password
        return created_user

    monkeypatch.setattr(users_router.s_users, "create_user", fake_create_user)

    response = client.post(
        "/users/",
        json={
            "nickname": "new-user",
            "first_name": "New",
            "last_name": "User",
            "password": "plain-password",
            "phone": "555-0100",
            "email": "new-user@example.com",
        },
    )

    assert response.status_code == 201, response.text
    assert captured["password"] == "plain-password"
    body = response.json()
    assert body["data"]["id"] == "created-user"
    assert "password" not in body["data"]


def test_create_user_rejects_missing_password():
    response = client.post(
        "/users/",
        json={
            "nickname": "new-user",
            "first_name": "New",
            "last_name": "User",
            "phone": "555-0100",
            "email": "new-user@example.com",
        },
    )

    assert response.status_code == 422


def test_update_user_uses_authenticated_requester(monkeypatch, make_user):
    requester = make_user(id="admin-user", role=constants.Role.ADMIN)
    updated_user = make_user(id="updated-user", nickname="changed")
    captured = {}

    app.dependency_overrides[users_router.get_current_user] = lambda: requester

    def fake_update_user(updated_user_id, updated_info, current_user):
        captured["updated_user_id"] = updated_user_id
        captured["updated_info"] = updated_info
        captured["requester"] = current_user
        return updated_user

    monkeypatch.setattr(users_router.s_users, "update_user", fake_update_user)

    response = client.patch("/users/updated-user", json={"nickname": "changed"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["nickname"] == "changed"
    assert captured["updated_user_id"] == "updated-user"
    assert captured["updated_info"].nickname == "changed"
    assert captured["requester"] is requester
