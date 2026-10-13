from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import app
from src import constants
from src.routers import users as users_router
from src.services import users as users_service


client = TestClient(app)


def _profile(
    *,
    department_id="support",
    availability_status=constants.AvailabilityStatus.AVAILABLE,
    max_active_tickets=5,
):
    now = constants.utc_now()
    return SimpleNamespace(
        user_id="agent-1",
        availability_status=availability_status,
        availability_reason=None,
        availability_note=None,
        unavailable_until=None,
        max_active_tickets=max_active_tickets,
        last_assigned_at=None,
        department_id=department_id,
        skill_ids=[],
        current_active_tickets=1,
        can_receive_new_tickets=True,
        created_at=now,
        updated_at=now,
    )


def test_assignment_candidates_requires_authentication():
    response = client.get("/users/assignment-candidates")

    assert response.status_code == 401


def test_assignment_candidates_rejects_non_manager(make_user, monkeypatch):
    requester = make_user(role=constants.Role.AGENT)
    app.dependency_overrides[users_router.get_current_user] = lambda: requester
    monkeypatch.setattr(users_service.operations, "get_user", lambda user_id: requester)

    response = client.get("/users/assignment-candidates")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "authorization_error"


def test_assignment_candidates_route_is_not_shadowed_by_user_id_route(make_user, monkeypatch):
    """`/users/assignment-candidates` must resolve to the literal route."""

    requester = make_user(id="manager-1", role=constants.Role.MANAGER)
    app.dependency_overrides[users_router.get_current_user] = lambda: requester
    monkeypatch.setattr(users_service.operations, "get_user", lambda user_id: requester)
    monkeypatch.setattr(
        users_service.operations,
        "get_assignment_candidates",
        lambda *args, **kwargs: [],
    )

    response = client.get("/users/assignment-candidates")

    assert response.status_code == 200
    assert response.json() == {"data": []}


def test_assignment_candidates_returns_eligible_agent_shape(make_user, monkeypatch):
    requester = make_user(id="manager-1", role=constants.Role.MANAGER)
    agent = make_user(id="agent-1", nickname="helpful", role=constants.Role.AGENT)
    app.dependency_overrides[users_router.get_current_user] = lambda: requester
    monkeypatch.setattr(users_service.operations, "get_user", lambda user_id: requester)
    monkeypatch.setattr(
        users_service.operations,
        "get_assignment_candidates",
        lambda *args, **kwargs: [(agent, _profile(), 2)],
    )

    response = client.get("/users/assignment-candidates?department_id=support")

    assert response.status_code == 200
    [candidate] = response.json()["data"]
    assert candidate == {
        "user_id": "agent-1",
        "nickname": "helpful",
        "first_name": "Test",
        "last_name": "User",
        "department_id": "support",
        "availability_status": constants.AvailabilityStatus.AVAILABLE.value,
        "current_active_tickets": 2,
        "max_active_tickets": 5,
        "can_receive_new_tickets": True,
    }


def test_assignment_candidates_forwards_filters(make_user, monkeypatch):
    requester = make_user(id="manager-1", role=constants.Role.MANAGER)
    app.dependency_overrides[users_router.get_current_user] = lambda: requester
    monkeypatch.setattr(users_service.operations, "get_user", lambda user_id: requester)
    captured = {}

    def fake_candidates(department_id, *, search=None, limit=50, offset=0):
        captured.update(
            department_id=department_id,
            search=search,
            limit=limit,
            offset=offset,
        )
        return []

    monkeypatch.setattr(
        users_service.operations, "get_assignment_candidates", fake_candidates
    )

    response = client.get(
        "/users/assignment-candidates",
        params={
            "department_id": "support",
            "search": "help",
            "limit": 5,
            "offset": 10,
        },
    )

    assert response.status_code == 200
    assert captured == {
        "department_id": "support",
        "search": "help",
        "limit": 5,
        "offset": 10,
    }
