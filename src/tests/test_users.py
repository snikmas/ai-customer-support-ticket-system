from fastapi.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from main import app
from src import constants
from src import models as api_models
from src.db import models as db_models
from src.db import operations
from src.routers import users as users_router
from src.exceptions.domain import AuthorizationError
from src.services import users as users_service
from src.exceptions.domain import UserAlreadyExistsError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
import pytest


client = TestClient(app)


def test_get_user_rejects_another_ordinary_user(monkeypatch, make_user):
    requester = make_user(id="requester", role=constants.Role.USER)
    target = make_user(id="target", role=constants.Role.USER)
    monkeypatch.setattr(users_service.operations, "get_user", lambda user_id: target)

    try:
        users_service.get_user(target.id, requester)
    except AuthorizationError:
        pass
    else:
        raise AssertionError("ordinary users must not read another user's private profile")


def test_get_user_allows_self_access(monkeypatch, make_user):
    requester = make_user(id="requester", role=constants.Role.USER)
    monkeypatch.setattr(users_service.operations, "get_user", lambda user_id: requester)

    assert users_service.get_user(requester.id, requester) is requester


def test_get_users_requires_authentication():
    response = client.get("/users/")

    assert response.status_code == 401


def test_get_users_returns_403_for_authenticated_user_without_permission(make_user):
    requester = make_user(role=constants.Role.USER)
    app.dependency_overrides[users_router.get_current_user] = lambda: requester

    response = client.get("/users/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "authorization_error"


def test_get_users_returns_current_service_shape(monkeypatch, make_user):
    requester = make_user(role=constants.Role.MANAGER)
    returned_user = make_user(id="visible-user", nickname="visible")

    app.dependency_overrides[users_router.get_current_user] = lambda: requester
    captured = {}

    def fake_get_all_users(current_user, limit, offset, sort_by, sort_order):
        captured.update(
            {
                "current_user": current_user,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "sort_order": sort_order,
            }
        )
        return [returned_user] if current_user is requester else []

    monkeypatch.setattr(users_router.s_users, "get_all_users", fake_get_all_users)

    response = client.get("/users/")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "data" in body
    assert body["data"][0]["id"] == "visible-user"
    assert "password" not in body["data"][0]
    assert captured == {
        "current_user": requester,
        "limit": constants.DEFAULT_PAGE_LIMIT,
        "offset": 0,
        "sort_by": constants.DEFAULT_SORT_BY,
        "sort_order": constants.DEFAULT_SORT_ORDER,
    }


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
            "password": "a secure plain passphrase",
            "phone": "+15550100",
            "email": "new-user@example.com",
        },
    )

    assert response.status_code == 201, response.text
    assert captured["password"] == "a secure plain passphrase"
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


def test_create_user_translates_duplicate_constraint_to_conflict(monkeypatch):
    user_create = users_router.models.UserCreate(
        nickname="duplicate-user",
        first_name="Duplicate",
        last_name="User",
        password="a secure plain passphrase",
        phone="+15550100",
        email="duplicate@example.com",
    )
    monkeypatch.setattr(users_service.operations, "get_users", lambda: [object()])
    monkeypatch.setattr(
        users_service.operations,
        "create_user",
        lambda *_: (_ for _ in ()).throw(IntegrityError("insert", {}, Exception("unique"))),
    )

    with pytest.raises(UserAlreadyExistsError):
        users_service.create_user(user_create)


def test_public_registration_always_creates_an_ordinary_user(monkeypatch):
    user_create = users_router.models.UserCreate(
        nickname="first-public-user",
        first_name="First",
        last_name="User",
        password="a secure plain passphrase",
        phone="+15550101",
        email="first-public-user@example.com",
    )
    captured = {}

    def fake_create_user(user, event):
        captured["role"] = user.role
        return user

    monkeypatch.setattr(users_service.operations, "create_user", fake_create_user)

    users_service.create_user(user_create)

    assert captured["role"] is constants.Role.USER


def test_delete_all_users_is_temporarily_unavailable(monkeypatch, make_user):
    requester = make_user(role=constants.Role.SUPER_ADMIN)
    app.dependency_overrides[users_router.get_current_user] = lambda: requester
    service_called = False

    def fake_delete_all_users(_requester):
        nonlocal service_called
        service_called = True

    monkeypatch.setattr(users_router.s_users, "delete_all_users", fake_delete_all_users)

    response = client.delete("/users/")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Bulk user deletion is temporarily unavailable"
    assert service_called is False


def test_concurrent_bootstrap_creates_exactly_one_superadmin(monkeypatch, tmp_path):
    test_engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'bootstrap.db'}",
        connect_args={"timeout": 5},
    )
    db_models.Base.metadata.create_all(test_engine)
    monkeypatch.setattr(operations, "engine", test_engine)

    def attempt(number: int) -> bool:
        now = datetime.now(timezone.utc)
        user = db_models.User(
            id=f"bootstrap-{number}",
            nickname=f"bootstrap-{number}",
            avatar_url=None,
            first_name="Bootstrap",
            last_name="Admin",
            phone=f"+1555010{number}",
            email=f"bootstrap-{number}@example.com",
            password="already-hashed",
            role=constants.Role.SUPER_ADMIN,
            updated_at=now,
            created_at=now,
        )
        event = api_models.Event(
            id=f"event-{number}",
            entity_type=constants.EntityType.USER,
            entity_id=user.id,
            actor_user_id=user.id,
            event_type=constants.EventType.USER_CREATED,
            old_value=None,
            new_value="{}",
            metadata=None,
            created_at=now,
        )
        return operations.create_initial_superadmin(user, event)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, (1, 2)))

    with Session(test_engine) as session:
        stored_users = session.scalar(select(func.count()).select_from(db_models.User))
        stored_superadmins = session.scalar(
            select(func.count())
            .select_from(db_models.User)
            .where(db_models.User.role == constants.Role.SUPER_ADMIN)
        )

    assert sorted(results) == [False, True]
    assert stored_users == 1
    assert stored_superadmins == 1


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
