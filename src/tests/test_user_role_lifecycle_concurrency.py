"""Regression coverage for user role/session lifecycle rules (Phase D).

Every test runs on SQLite and on PostgreSQL 16 (when TEST_POSTGRES_URL is set)
through the shared ``mutation_engine`` fixture. Concurrency is forced with a
``threading.Barrier`` and explicit lock/statement timeouts, never with sleeps,
so a deadlock or a lost update becomes a clear failure.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from src import constants
from src import models as api_models
from src.core.security import hash_password
from src.db import models as db_models
from src.db import operations
from src.exceptions.domain import (
    AgentHasActiveTicketsError,
    FinalAdminAccessError,
    LastSuperAdminError,
    RefreshSessionRevokedError,
)
from src.services import auth as auth_service


def _now():
    return datetime.now(timezone.utc)


def _department(department_id: str, now: datetime) -> db_models.Department:
    return db_models.Department(
        id=department_id,
        name=department_id.title(),
        normalized_name=department_id,
        description=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _user(
    user_id: str,
    role: constants.Role,
    now: datetime,
    *,
    user_status: constants.UserStatus = constants.UserStatus.ACTIVE,
    deleted_at: datetime | None = None,
    password: str = "hashed-password",
) -> db_models.User:
    return db_models.User(
        id=user_id,
        nickname=user_id,
        avatar_url=None,
        first_name="Test",
        last_name="User",
        phone=f"phone-{user_id}",
        email=f"{user_id}@example.com",
        role=role,
        password=password,
        updated_at=now,
        created_at=now,
        deleted_at=deleted_at,
        user_status=user_status,
    )


def _profile(
    user_id: str,
    department_id: str | None,
    now: datetime,
    *,
    capacity: int = 5,
    availability: constants.AvailabilityStatus = constants.AvailabilityStatus.AVAILABLE,
) -> db_models.AgentProfile:
    return db_models.AgentProfile(
        user_id=user_id,
        availability_status=availability,
        availability_reason=None,
        availability_note=None,
        unavailable_until=None,
        max_active_tickets=capacity,
        last_assigned_at=None,
        department_id=department_id,
        created_at=now,
        updated_at=now,
    )


def _ticket(
    ticket_id: str,
    now: datetime,
    *,
    assigned_agent_id: str | None = None,
    status: constants.Status = constants.Status.NEW,
    department_id: str = "support",
) -> db_models.Ticket:
    return db_models.Ticket(
        id=ticket_id,
        title="Ticket",
        description="Description",
        category=constants.Category.ACCOUNT_ACCESS,
        tags=None,
        department_id=department_id,
        assigned_agent_id=assigned_agent_id,
        creator_user_id="customer",
        status=status,
        priority=constants.Priority.NORMAL,
        updated_at=now,
        created_at=now,
        due_at=constants.calculate_sla_due_at(status, now),
        deleted_at=None,
    )


def _user_event(event_id: str, target_id: str, actor_id: str, now: datetime):
    return api_models.Event(
        id=event_id,
        entity_type=constants.EntityType.USER,
        entity_id=target_id,
        actor_user_id=actor_id,
        event_type=constants.EventType.USER_UPDATED,
        old_value=None,
        new_value="{}",
        metadata=None,
        created_at=now,
    )


# ---------------------------------------------------------------- last admin


def _seed_superadmins(engine, now):
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _user("super1", constants.Role.SUPER_ADMIN, now),
                _user("super2", constants.Role.SUPER_ADMIN, now),
            ]
        )


def _concurrent(engine, first, second):
    barrier = threading.Barrier(2)

    def guarded(call):
        barrier.wait(timeout=15)
        return call()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(guarded, first)
        second_future = executor.submit(guarded, second)
        first_error = first_future.exception(timeout=20)
        second_error = second_future.exception(timeout=20)
    return first_error, second_error


def test_concurrent_superadmin_self_demotion_keeps_one(mutation_engine):
    engine = mutation_engine
    now = _now()
    _seed_superadmins(engine, now)
    guards = operations.UserLifecycleGuards(protect_last_super_admin=True)

    def demote(user_id):
        return operations.update_user(
            user_id,
            {"role": constants.Role.ADMIN},
            _user_event(f"event-{user_id}", user_id, user_id, now),
            guards=guards,
        )

    first_error, second_error = _concurrent(
        engine, lambda: demote("super1"), lambda: demote("super2")
    )

    errors = [error for error in (first_error, second_error) if error is not None]
    assert len(errors) == 1, (first_error, second_error)
    assert isinstance(errors[0], LastSuperAdminError)
    assert operations.count_active_superadmins() == 1


def test_concurrent_superadmin_self_delete_keeps_one(mutation_engine):
    engine = mutation_engine
    now = _now()
    _seed_superadmins(engine, now)
    guards = operations.UserLifecycleGuards(protect_last_super_admin=True)

    def remove(user_id):
        return operations.delete_user(
            user_id,
            {"deleted_at": now, "updated_at": now, "user_status": constants.UserStatus.DELETED},
            _user_event(f"event-{user_id}", user_id, user_id, now),
            guards=guards,
        )

    first_error, second_error = _concurrent(
        engine, lambda: remove("super1"), lambda: remove("super2")
    )

    errors = [error for error in (first_error, second_error) if error is not None]
    assert len(errors) == 1, (first_error, second_error)
    assert isinstance(errors[0], LastSuperAdminError)
    assert operations.count_active_superadmins() == 1


def test_concurrent_superadmin_self_deactivation_keeps_one(mutation_engine):
    engine = mutation_engine
    now = _now()
    _seed_superadmins(engine, now)
    guards = operations.UserLifecycleGuards(protect_last_super_admin=True)

    def deactivate(user_id):
        return operations.update_user(
            user_id,
            {"user_status": constants.UserStatus.BANNED},
            _user_event(f"event-{user_id}", user_id, user_id, now),
            guards=guards,
        )

    first_error, second_error = _concurrent(
        engine, lambda: deactivate("super1"), lambda: deactivate("super2")
    )

    errors = [error for error in (first_error, second_error) if error is not None]
    assert len(errors) == 1, (first_error, second_error)
    assert isinstance(errors[0], LastSuperAdminError)
    assert operations.count_active_superadmins() == 1


def test_concurrent_admin_self_lockout_keeps_one_administrator(mutation_engine):
    engine = mutation_engine
    now = _now()
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _user("admin1", constants.Role.ADMIN, now),
                _user("admin2", constants.Role.ADMIN, now),
            ]
        )
    guards = operations.UserLifecycleGuards(protect_final_admin_access=True)

    def demote(user_id):
        return operations.update_user(
            user_id,
            {"role": constants.Role.USER},
            _user_event(f"event-{user_id}", user_id, user_id, now),
            guards=guards,
        )

    first_error, second_error = _concurrent(
        engine, lambda: demote("admin1"), lambda: demote("admin2")
    )

    errors = [error for error in (first_error, second_error) if error is not None]
    assert len(errors) == 1, (first_error, second_error)
    assert isinstance(errors[0], FinalAdminAccessError)
    assert operations.count_active_administrators() == 1


# ------------------------------------------------------- transition into agent


@pytest.mark.parametrize(
    "source_role",
    [
        constants.Role.USER,
        constants.Role.MANAGER,
        constants.Role.ADMIN,
        constants.Role.AGENT_READONLY,
        constants.Role.SUPER_ADMIN,
    ],
)
def test_transition_into_agent_creates_configurable_profile(
    mutation_engine,
    source_role,
):
    engine = mutation_engine
    now = _now()
    with Session(engine) as session, session.begin():
        session.add(_department("support", now))
        session.add(_user("promoted", source_role, now))

    updated = operations.update_user(
        "promoted",
        {"role": constants.Role.AGENT},
        _user_event("promote-event", "promoted", "promoted", now),
    )

    assert updated.role is constants.Role.AGENT
    profile = operations.get_agent_profile("promoted")
    assert profile is not None
    assert profile.availability_status is constants.AvailabilityStatus.OFFLINE
    assert profile.availability_reason == "profile_setup_required"
    assert profile.department_id is None
    assert profile.max_active_tickets == 0

    configured = operations.update_agent_profile(
        "promoted",
        {
            "department_id": "support",
            "max_active_tickets": 3,
            "availability_status": constants.AvailabilityStatus.AVAILABLE,
            "availability_reason": None,
            "availability_note": None,
            "unavailable_until": None,
            "updated_at": now,
        },
        _user_event("config-event", "promoted", "promoted", now),
    )
    assert configured is not None
    assert configured.department_id == "support"
    assert configured.max_active_tickets == 3
    assert configured.availability_status is constants.AvailabilityStatus.AVAILABLE


# ------------------------------------------------------- transition out of agent


@pytest.mark.parametrize("mutation", ["demote", "ban", "delete"])
def test_agent_with_active_work_cannot_leave_role(mutation_engine, mutation):
    engine = mutation_engine
    now = _now()
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _department("support", now),
                _user("customer", constants.Role.USER, now),
                _user("agent", constants.Role.AGENT, now),
            ]
        )
        session.flush()
        session.add(_profile("agent", "support", now))
        session.flush()
        session.add(
            _ticket("ticket", now, assigned_agent_id="agent", status=constants.Status.IN_PROGRESS)
        )

    def apply(index: int):
        if mutation == "demote":
            return operations.update_user(
                "agent",
                {"role": constants.Role.AGENT_READONLY},
                _user_event(f"event-{index}", "agent", "agent", now),
            )
        if mutation == "ban":
            return operations.update_user(
                "agent",
                {"user_status": constants.UserStatus.BANNED},
                _user_event(f"event-{index}", "agent", "agent", now),
            )
        return operations.delete_user(
            "agent",
            {"deleted_at": now, "updated_at": now, "user_status": constants.UserStatus.DELETED},
            _user_event(f"event-{index}", "agent", "agent", now),
        )

    with pytest.raises(AgentHasActiveTicketsError):
        apply(1)
    stored = operations.get_user("agent")
    assert stored.role is constants.Role.AGENT
    assert stored.user_status is constants.UserStatus.ACTIVE
    assert stored.deleted_at is None

    operations.update_ticket(
        "ticket",
        {"status": constants.Status.RESOLVED, "assigned_agent_id": None},
    )

    apply(2)
    stored = operations.get_user("agent")
    if mutation == "demote":
        assert stored.role is constants.Role.AGENT_READONLY
    elif mutation == "ban":
        assert stored.user_status is constants.UserStatus.BANNED
    else:
        assert stored.deleted_at is not None
    profile = operations.get_agent_profile("agent")
    assert profile is None or profile.availability_status is constants.AvailabilityStatus.OFFLINE


def test_concurrent_routing_and_demotion_never_strand_work(
    mutation_engine,
    monkeypatch,
):
    engine = mutation_engine
    now = _now()
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _department("support", now),
                _user("customer", constants.Role.USER, now),
                _user("agent", constants.Role.AGENT, now),
            ]
        )
        session.flush()
        session.add(_profile("agent", "support", now))
        session.flush()
        session.add(_ticket("ticket", now))

    # Force the unsafe order: the router takes its locks and assigns the ticket
    # first, while the demotion is already waiting for the same rows. Holding
    # the router inside its transaction (before commit) is a controlled
    # transaction boundary, not a sleep.
    routing_locked = threading.Event()
    release_routing = threading.Event()
    original_record = operations._record_agent_received_ticket

    def paused_record(session, agent_user_id, assigned_at):
        routing_locked.set()
        assert release_routing.wait(timeout=15), "routing was never released"
        return original_record(session, agent_user_id, assigned_at)

    monkeypatch.setattr(operations, "_record_agent_received_ticket", paused_record)

    def route():
        return operations.try_route_ticket("ticket")

    def demote():
        assert routing_locked.wait(timeout=15), "routing never locked"
        return operations.update_user(
            "agent",
            {"role": constants.Role.USER},
            _user_event("demote-event", "agent", "agent", now),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        route_future = executor.submit(route)
        assert routing_locked.wait(timeout=15), "routing never started"
        demote_future = executor.submit(demote)
        release_routing.set()
        route_error = route_future.exception(timeout=20)
        demote_error = demote_future.exception(timeout=20)

    stored_ticket = operations.get_ticket("ticket")
    stored_agent = operations.get_user("agent")

    assert route_error is None, route_error
    assert stored_ticket.assigned_agent_id == "agent"
    assert isinstance(demote_error, AgentHasActiveTicketsError)
    assert stored_agent.role is constants.Role.AGENT


# --------------------------------------------------------------- sessions


def _seed_user_with_session(engine, now):
    raw_session = None
    with Session(engine) as session, session.begin():
        session.add(_user("customer", constants.Role.USER, now))
    created = auth_service.create_refresh_session_for_user("customer")
    assert created is not None
    raw_session = created.refresh_token
    return created.refresh_session_id, raw_session


def test_password_change_revokes_every_refresh_session(mutation_engine):
    engine = mutation_engine
    now = _now()
    session_id, raw_session = _seed_user_with_session(engine, now)

    operations.update_user(
        "customer",
        {"password": hash_password("brand-new-password")},
        _user_event("password-event", "customer", "customer", now),
        revoke_refresh_sessions=True,
    )

    stored_session = operations.get_refresh_session_by_id(session_id)
    assert stored_session.revoked_at is not None
    with pytest.raises(RefreshSessionRevokedError):
        auth_service.verify_refresh_session(raw_session)

    relogged = auth_service.login_user("customer@example.com", "brand-new-password")
    assert relogged is not None
    assert relogged.id == "customer"


def test_password_change_race_with_rotation_revokes_all_tokens(mutation_engine):
    engine = mutation_engine
    now = _now()
    session_id, raw_session = _seed_user_with_session(engine, now)
    snapshot = operations.get_refresh_session_by_id(session_id)

    barrier = threading.Barrier(2)

    def change_password():
        barrier.wait(timeout=15)
        return operations.update_user(
            "customer",
            {"password": hash_password("rotated-password")},
            _user_event("password-race", "customer", "customer", now),
            revoke_refresh_sessions=True,
        )

    def rotate():
        barrier.wait(timeout=15)
        return auth_service.rotate_refresh_session(snapshot)

    with ThreadPoolExecutor(max_workers=2) as executor:
        change_future = executor.submit(change_password)
        rotate_future = executor.submit(rotate)
        change_error = change_future.exception(timeout=20)
        rotate_error = rotate_future.exception(timeout=20)

    assert change_error is None, change_error
    assert rotate_error is None, rotate_error

    stored_session = operations.get_refresh_session_by_id(session_id)
    assert stored_session.revoked_at is not None, "no refresh session may survive"
    with pytest.raises(RefreshSessionRevokedError):
        auth_service.verify_refresh_session(raw_session)
