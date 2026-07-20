from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from main import app
from src import constants


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def make_user():
    def _make_user(
        *,
        id="user-1",
        nickname="test-user",
        role=constants.Role.USER,
        user_status=constants.UserStatus.ACTIVE,
    ):
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=id,
            nickname=nickname,
            avatar_url=None,
            first_name="Test",
            last_name="User",
            phone=f"phone-{id}",
            email=f"{id}@example.com",
            role=role,
            password="hashed-password",
            updated_at=now,
            created_at=now,
            due_at=None,
            deleted_at=None,
            user_status=user_status,
        )

    return _make_user


@pytest.fixture
def make_ticket():
    def _make_ticket(
        *,
        id="ticket-1",
        creator_user_id="user-1",
        assigned_agent_id=None,
        status=constants.Status.NEW,
        priority=constants.Priority.NORMAL,
        tags=None,
    ):
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=id,
            title="Test ticket",
            description="Test description",
            category=constants.Category.ACCOUNT_ACCESS,
            tags=tags if tags is not None else [constants.Tag.API_KEY],
            assigned_agent_id=assigned_agent_id,
            creator_user_id=creator_user_id,
            status=status,
            priority=priority,
            updated_at=now,
            created_at=now,
            deleted_at=None,
        )

    return _make_ticket
