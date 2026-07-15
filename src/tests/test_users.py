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


def _stored_user(*, user_id: str, role: constants.Role, now: datetime) -> db_models.User:
    return db_models.User(
        id=user_id,
        nickname=user_id,
        avatar_url=None,
        first_name="Test",
        last_name="User",
        phone=f"phone-{user_id}",
        email=f"{user_id}@example.com",
        role=role,
        password="hashed-password",
        updated_at=now,
        created_at=now,
        deleted_at=None,
        user_status=constants.UserStatus.ACTIVE,
    )


def _role_update_event(*, event_id: str, target_id: str, actor_id: str, now: datetime):
    return api_models.Event(
        id=event_id,
        entity_type=constants.EntityType.USER,
        entity_id=target_id,
        actor_user_id=actor_id,
        event_type=constants.EventType.USER_UPDATED,
        old_value='{"role": "agent"}',
        new_value='{"role": "manager"}',
        metadata=None,
        created_at=now,
    )


def _role_lifecycle_engine(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'roles.db'}")
    db_models.Base.metadata.create_all(test_engine)
    monkeypatch.setattr(operations, "engine", test_engine)
    return test_engine


def test_user_to_agent_creates_non_routing_profile(monkeypatch, tmp_path):
    test_engine = _role_lifecycle_engine(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)

    with Session(test_engine) as session, session.begin():
        session.add_all(
            [
                _stored_user(user_id="admin", role=constants.Role.ADMIN, now=now),
                _stored_user(user_id="future-agent", role=constants.Role.USER, now=now),
            ]
        )

    updated_user = operations.update_user(
        "future-agent",
        {"role": constants.Role.AGENT},
        _role_update_event(
            event_id="promote-event",
            target_id="future-agent",
            actor_id="admin",
            now=now,
        ),
    )

    with Session(test_engine) as session:
        profile = session.get(db_models.AgentProfile, "future-agent")
        event_count = session.scalar(select(func.count()).select_from(db_models.Event))

        assert updated_user.role is constants.Role.AGENT
        assert profile is not None
        assert profile.availability_status is constants.AvailabilityStatus.OFFLINE
        assert profile.availability_reason == "profile_setup_required"
        assert profile.max_active_tickets == 0
        assert profile.department_id is None
        assert "current_ticket_count" not in db_models.AgentProfile.__table__.columns
        assert event_count == 1


def test_active_ticket_count_uses_settled_workload_rule(monkeypatch, tmp_path):
    test_engine = _role_lifecycle_engine(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    active_statuses = [
        constants.Status.OPEN,
        constants.Status.IN_PROGRESS,
        constants.Status.PENDING,
        constants.Status.ON_HOLD,
        constants.Status.REOPENED,
    ]
    ignored_statuses = [
        constants.Status.NEW,
        constants.Status.RESOLVED,
        constants.Status.CLOSED,
    ]

    with Session(test_engine) as session, session.begin():
        agent = _stored_user(user_id="agent", role=constants.Role.AGENT, now=now)
        customer = _stored_user(user_id="customer", role=constants.Role.USER, now=now)
        session.add_all([agent, customer])
        session.add_all(
            [
                db_models.Ticket(
                    id=f"active-{index}",
                    title="Ticket",
                    description="Description",
                    category=constants.Category.ACCOUNT_ACCESS,
                    tags=None,
                    assigned_agent_id=agent.id,
                    creator_user_id=customer.id,
                    status=status,
                    priority=constants.Priority.NORMAL,
                    updated_at=now,
                    created_at=now,
                    deleted_at=None,
                )
                for index, status in enumerate(active_statuses)
            ]
        )
        session.add_all(
            [
                db_models.Ticket(
                    id=f"ignored-{index}",
                    title="Ticket",
                    description="Description",
                    category=constants.Category.ACCOUNT_ACCESS,
                    tags=None,
                    assigned_agent_id=agent.id,
                    creator_user_id=customer.id,
                    status=status,
                    priority=constants.Priority.NORMAL,
                    updated_at=now,
                    created_at=now,
                    deleted_at=None,
                )
                for index, status in enumerate(ignored_statuses)
            ]
        )
        session.add(
            db_models.Ticket(
                id="soft-deleted-active",
                title="Ticket",
                description="Description",
                category=constants.Category.ACCOUNT_ACCESS,
                tags=None,
                assigned_agent_id=agent.id,
                creator_user_id=customer.id,
                status=constants.Status.OPEN,
                priority=constants.Priority.NORMAL,
                updated_at=now,
                created_at=now,
                deleted_at=now,
            )
        )

    assert operations.count_active_assigned_tickets("agent") == 5


def test_agent_to_manager_conflict_is_atomic_and_returns_http_409(monkeypatch, tmp_path, make_user):
    test_engine = _role_lifecycle_engine(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)

    with Session(test_engine) as session, session.begin():
        admin = _stored_user(user_id="admin", role=constants.Role.ADMIN, now=now)
        agent = _stored_user(user_id="agent", role=constants.Role.AGENT, now=now)
        customer = _stored_user(user_id="customer", role=constants.Role.USER, now=now)
        session.add_all([admin, agent, customer])
        session.add(
            db_models.AgentProfile(
                user_id=agent.id,
                availability_status=constants.AvailabilityStatus.AVAILABLE,
                availability_reason=None,
                availability_note=None,
                unavailable_until=None,
                max_active_tickets=5,
                department_id="support",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            db_models.Ticket(
                id="active-ticket",
                title="Ticket",
                description="Description",
                category=constants.Category.ACCOUNT_ACCESS,
                tags=None,
                assigned_agent_id=agent.id,
                creator_user_id=customer.id,
                status=constants.Status.IN_PROGRESS,
                priority=constants.Priority.NORMAL,
                updated_at=now,
                created_at=now,
                deleted_at=None,
            )
        )

    app.dependency_overrides[users_router.get_current_user] = lambda: make_user(
        id="admin",
        role=constants.Role.ADMIN,
    )
    response = client.patch("/users/agent", json={"role": constants.Role.MANAGER.value})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "agent_has_active_tickets"
    assert "1 active assigned ticket(s)" in response.json()["error"]["message"]
    with Session(test_engine) as session:
        stored_agent = session.get(db_models.User, "agent")
        profile = session.get(db_models.AgentProfile, "agent")
        event_count = session.scalar(select(func.count()).select_from(db_models.Event))
        assert stored_agent.role is constants.Role.AGENT
        assert profile.availability_status is constants.AvailabilityStatus.AVAILABLE
        assert event_count == 0


def test_agent_to_manager_preserves_profile_but_disables_routing(monkeypatch, tmp_path):
    test_engine = _role_lifecycle_engine(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)

    with Session(test_engine) as session, session.begin():
        session.add_all(
            [
                _stored_user(user_id="admin", role=constants.Role.ADMIN, now=now),
                _stored_user(user_id="agent", role=constants.Role.AGENT, now=now),
            ]
        )
        session.add(
            db_models.AgentProfile(
                user_id="agent",
                availability_status=constants.AvailabilityStatus.AVAILABLE,
                availability_reason=None,
                availability_note="experienced in auth",
                unavailable_until=None,
                max_active_tickets=7,
                department_id="platform-support",
                created_at=now,
                updated_at=now,
            )
        )

    operations.update_user(
        "agent",
        {"role": constants.Role.MANAGER},
        _role_update_event(
            event_id="manager-event",
            target_id="agent",
            actor_id="admin",
            now=now,
        ),
    )

    with Session(test_engine) as session:
        stored_agent = session.get(db_models.User, "agent")
        profile = session.get(db_models.AgentProfile, "agent")
        assert stored_agent.role is constants.Role.MANAGER
        assert profile.availability_status is constants.AvailabilityStatus.OFFLINE
        assert profile.availability_reason == "role_changed_to_manager"
        assert profile.availability_note == "experienced in auth"
        assert profile.max_active_tickets == 7
        assert profile.department_id == "platform-support"
