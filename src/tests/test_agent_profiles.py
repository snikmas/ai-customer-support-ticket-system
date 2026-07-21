import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from main import app
from src import constants
from src.db import models as db_models
from src.db import operations
from src.routers import users as users_router


client = TestClient(app)


def _user(user_id: str, role: constants.Role, now: datetime) -> db_models.User:
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


def _profile(
    user_id: str,
    now: datetime,
    *,
    status: constants.AvailabilityStatus = constants.AvailabilityStatus.AVAILABLE,
    reason: str | None = None,
    note: str | None = None,
    unavailable_until: datetime | None = None,
    capacity: int = 3,
    last_assigned_at: datetime | None = None,
) -> db_models.AgentProfile:
    return db_models.AgentProfile(
        user_id=user_id,
        availability_status=status,
        availability_reason=reason,
        availability_note=note,
        unavailable_until=unavailable_until,
        max_active_tickets=capacity,
        last_assigned_at=last_assigned_at,
        department_id="support",
        created_at=now,
        updated_at=now,
    )


def _prepare_database(monkeypatch, tmp_path):
    from sqlalchemy import create_engine

    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'profiles.db'}")
    db_models.Base.metadata.create_all(test_engine)
    now = datetime.now(timezone.utc)
    with Session(test_engine) as session, session.begin():
        session.add(
            db_models.Department(
                id="support",
                name="Support",
                normalized_name="support",
                description=None,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
        )
    monkeypatch.setattr(operations, "engine", test_engine)
    return test_engine


def _ticket(
    ticket_id: str,
    creator_id: str,
    now: datetime,
    *,
    assigned_agent_id: str | None = None,
    status: constants.Status = constants.Status.NEW,
) -> db_models.Ticket:
    return db_models.Ticket(
        id=ticket_id,
        title="Ticket",
        description="Description",
        category=constants.Category.ACCOUNT_ACCESS,
        tags=None,
        department_id="support",
        assigned_agent_id=assigned_agent_id,
        creator_user_id=creator_id,
        status=status,
        priority=constants.Priority.NORMAL,
        updated_at=now,
        created_at=now,
        deleted_at=None,
    )


def _seed_routing_pool(
    test_engine,
    now: datetime,
    profiles: list[db_models.AgentProfile],
    tickets: list[db_models.Ticket] | None = None,
) -> None:
    with Session(test_engine) as session, session.begin():
        session.add(_user("customer", constants.Role.USER, now))
        session.add_all(
            _user(profile.user_id, constants.Role.AGENT, now)
            for profile in profiles
        )
        session.add_all(profiles)
        session.add_all(tickets or [])
        session.add(
            _ticket("routing-ticket", "customer", now)
        )


def test_least_loaded_agent_wins_before_tie_breakers(monkeypatch, tmp_path):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    profiles = [
        _profile("agent-busy", now, last_assigned_at=None),
        _profile("agent-free", now, last_assigned_at=now),
    ]
    tickets = [
        _ticket(
            "active-ticket",
            "customer",
            now,
            assigned_agent_id="agent-busy",
            status=constants.Status.OPEN,
        )
    ]
    _seed_routing_pool(test_engine, now, profiles, tickets)

    selected = operations.get_least_loaded_eligible_agent("routing-ticket")

    assert selected is not None
    assert selected.id == "agent-free"


def test_routing_query_uses_only_current_hard_eligibility_pool(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    eligible = _user("eligible", constants.Role.AGENT, now)
    inactive = _user("inactive", constants.Role.AGENT, now)
    inactive.user_status = constants.UserStatus.BANNED
    deleted = _user("deleted", constants.Role.AGENT, now)
    deleted.deleted_at = now

    with Session(test_engine) as session, session.begin():
        session.add_all(
            [
                _user("customer", constants.Role.USER, now),
                eligible,
                inactive,
                deleted,
                _user("manager", constants.Role.MANAGER, now),
                _user("unavailable", constants.Role.AGENT, now),
                _user("at-capacity", constants.Role.AGENT, now),
            ]
        )
        session.add_all(
            [
                _profile("eligible", now),
                _profile("inactive", now),
                _profile("deleted", now),
                _profile("manager", now),
                _profile(
                    "unavailable",
                    now,
                    status=constants.AvailabilityStatus.OFFLINE,
                ),
                _profile("at-capacity", now, capacity=0),
            ]
        )
        session.add(_ticket("routing-ticket", "customer", now))

    selected = operations.get_least_loaded_eligible_agent("routing-ticket")

    assert selected is not None
    assert selected.id == "eligible"


def test_never_assigned_agent_wins_equal_workload_tie(monkeypatch, tmp_path):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed_routing_pool(
        test_engine,
        now,
        [
            _profile("agent-recent", now, last_assigned_at=now),
            _profile("agent-never", now, last_assigned_at=None),
        ],
    )

    selected = operations.get_least_loaded_eligible_agent("routing-ticket")

    assert selected is not None
    assert selected.id == "agent-never"


def test_oldest_last_assignment_wins_next_tie(monkeypatch, tmp_path):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed_routing_pool(
        test_engine,
        now,
        [
            _profile("agent-newer", now, last_assigned_at=now - timedelta(hours=1)),
            _profile("agent-older", now, last_assigned_at=now - timedelta(days=1)),
        ],
    )

    selected = operations.get_least_loaded_eligible_agent("routing-ticket")

    assert selected is not None
    assert selected.id == "agent-older"


def test_user_id_breaks_final_routing_tie(monkeypatch, tmp_path):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    same_assignment_time = now - timedelta(hours=1)
    _seed_routing_pool(
        test_engine,
        now,
        [
            _profile("agent-b", now, last_assigned_at=same_assignment_time),
            _profile("agent-a", now, last_assigned_at=same_assignment_time),
        ],
    )

    selected = operations.get_least_loaded_eligible_agent("routing-ticket")

    assert selected is not None
    assert selected.id == "agent-a"


def test_receiving_ticket_updates_only_new_owner_last_assigned_at(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed_routing_pool(
        test_engine,
        now,
        [_profile("agent-a", now), _profile("agent-b", now)],
        [_ticket("ticket", "customer", now)],
    )

    assigned = operations.assign_ticket("ticket", "agent-a")
    assert assigned is not None
    with Session(test_engine) as session:
        first_assignment = session.get(
            db_models.AgentProfile,
            "agent-a",
        ).last_assigned_at
        assert first_assignment is not None

    reassigned = operations.assign_ticket("ticket", "agent-b")
    assert reassigned is not None
    with Session(test_engine) as session:
        agent_a = session.get(db_models.AgentProfile, "agent-a")
        agent_b = session.get(db_models.AgentProfile, "agent-b")
        assert agent_a.last_assigned_at == first_assignment
        assert agent_b.last_assigned_at is not None

    operations.update_ticket(
        "ticket",
        {"status": constants.Status.RESOLVED, "assigned_agent_id": None},
    )
    with Session(test_engine) as session:
        agent_a = session.get(db_models.AgentProfile, "agent-a")
        agent_b = session.get(db_models.AgentProfile, "agent-b")
        assert agent_a.last_assigned_at == first_assignment
        assert agent_b.last_assigned_at is not None


def test_agent_can_pause_self_and_change_is_audited(monkeypatch, tmp_path, make_user):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=1)
    with Session(test_engine) as session, session.begin():
        session.add(_user("agent", constants.Role.AGENT, now))
        session.add(_profile("agent", now))

    app.dependency_overrides[users_router.get_current_user] = lambda: make_user(
        id="agent",
        role=constants.Role.AGENT,
    )
    response = client.patch(
        "/users/agent/availability",
        json={
            "availability_status": "paused",
            "reason": "MEETING",
            "note": "Team planning",
            "unavailable_until": until.isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["availability_status"] == "paused"
    assert response.json()["data"]["can_receive_new_tickets"] is False
    with Session(test_engine) as session:
        profile = session.get(db_models.AgentProfile, "agent")
        event = session.scalar(select(db_models.Event))
        assert profile.availability_reason == "MEETING"
        assert profile.availability_note == "Team planning"
        assert event.actor_user_id == "agent"
        assert event.entity_id == "agent"
        assert event.entity_type is constants.EntityType.AGENT_PROFILE
        assert event.event_type is constants.EventType.AGENT_AVAILABILITY_CHANGED
        assert json.loads(event.new_value)["availability_reason"] == "MEETING"
        assert event.created_at is not None


def test_returning_available_clears_old_absence_context(monkeypatch, tmp_path, make_user):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    with Session(test_engine) as session, session.begin():
        session.add(_user("agent", constants.Role.AGENT, now))
        session.add(
            _profile(
                "agent",
                now,
                status=constants.AvailabilityStatus.OFFLINE,
                reason="PERSONAL_LEAVE",
                note="Back tomorrow",
                unavailable_until=now + timedelta(days=1),
            )
        )

    app.dependency_overrides[users_router.get_current_user] = lambda: make_user(
        id="agent",
        role=constants.Role.AGENT,
    )
    response = client.patch(
        "/users/agent/availability",
        json={
            "availability_status": "available",
            "reason": "OTHER",
            "note": "This must be discarded",
            "unavailable_until": (now + timedelta(days=2)).isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["availability_reason"] is None
    assert data["availability_note"] is None
    assert data["unavailable_until"] is None
    assert data["can_receive_new_tickets"] is True


def test_manager_can_override_availability_but_another_agent_cannot(
    monkeypatch,
    tmp_path,
    make_user,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    with Session(test_engine) as session, session.begin():
        session.add_all(
            [
                _user("agent", constants.Role.AGENT, now),
                _user("other-agent", constants.Role.AGENT, now),
                _user("manager", constants.Role.MANAGER, now),
            ]
        )
        session.add_all([_profile("agent", now), _profile("other-agent", now)])

    app.dependency_overrides[users_router.get_current_user] = lambda: make_user(
        id="other-agent",
        role=constants.Role.AGENT,
    )
    forbidden = client.patch(
        "/users/agent/availability",
        json={"availability_status": "offline", "reason": "SHIFT_ENDED"},
    )
    assert forbidden.status_code == 403

    app.dependency_overrides[users_router.get_current_user] = lambda: make_user(
        id="manager",
        role=constants.Role.MANAGER,
    )
    allowed = client.patch(
        "/users/agent/availability",
        json={"availability_status": "offline", "reason": "SHIFT_ENDED"},
    )
    assert allowed.status_code == 200, allowed.text
    with Session(test_engine) as session:
        event = session.scalar(select(db_models.Event))
        assert event.actor_user_id == "manager"


def test_capacity_is_manager_only_and_lowering_it_keeps_assignments(
    monkeypatch,
    tmp_path,
    make_user,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    with Session(test_engine) as session, session.begin():
        session.add_all(
            [
                _user("agent", constants.Role.AGENT, now),
                _user("manager", constants.Role.MANAGER, now),
                _user("customer", constants.Role.USER, now),
            ]
        )
        session.add(_profile("agent", now, capacity=5))
        for number in (1, 2):
            session.add(
                db_models.Ticket(
                    id=f"ticket-{number}",
                    title="Ticket",
                    description="Description",
                    category=constants.Category.ACCOUNT_ACCESS,
                    tags=None,
                    assigned_agent_id="agent",
                    creator_user_id="customer",
                    status=constants.Status.IN_PROGRESS,
                    priority=constants.Priority.NORMAL,
                    updated_at=now,
                    created_at=now,
                    deleted_at=None,
                )
            )

    app.dependency_overrides[users_router.get_current_user] = lambda: make_user(
        id="agent",
        role=constants.Role.AGENT,
    )
    forbidden = client.patch(
        "/users/agent/agent-profile",
        json={"max_active_tickets": 1},
    )
    assert forbidden.status_code == 403

    app.dependency_overrides[users_router.get_current_user] = lambda: make_user(
        id="manager",
        role=constants.Role.MANAGER,
    )
    response = client.patch(
        "/users/agent/agent-profile",
        json={"max_active_tickets": 1},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["current_active_tickets"] == 2
    assert data["max_active_tickets"] == 1
    assert data["can_receive_new_tickets"] is False
    with Session(test_engine) as session:
        assigned_count = session.scalar(
            select(func.count())
            .select_from(db_models.Ticket)
            .where(db_models.Ticket.assigned_agent_id == "agent")
        )
        profile = session.get(db_models.AgentProfile, "agent")
        event = session.scalar(select(db_models.Event))
        assert assigned_count == 2
        assert profile.department_id == "support"
        assert event.event_type is constants.EventType.AGENT_PROFILE_UPDATED
        assert event.actor_user_id == "manager"


def test_availability_input_rejects_long_notes_and_unknown_reason(
    monkeypatch,
    make_user,
):
    app.dependency_overrides[users_router.get_current_user] = lambda: make_user(
        id="agent",
        role=constants.Role.AGENT,
    )

    long_note = client.patch(
        "/users/agent/availability",
        json={"availability_status": "paused", "note": "x" * 201},
    )
    unknown_reason = client.patch(
        "/users/agent/availability",
        json={"availability_status": "paused", "reason": "SICK_WITH_DETAILS"},
    )

    assert long_note.status_code == 422
    assert unknown_reason.status_code == 422
