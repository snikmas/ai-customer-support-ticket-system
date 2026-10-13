"""Concurrency regressions for atomic ticket mutations (Phase C).

Each test runs on SQLite and on PostgreSQL 16 (when TEST_POSTGRES_URL is set).
The PostgreSQL variant is skipped cleanly when the environment variable is
absent, so the default suite still passes with no PostgreSQL configured.

Determinism comes from threading events/barriers and explicit lock/statement
timeouts, never from sleeps: the interleaving is forced, not timed.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src import constants, models
from src.db import models as db_models
from src.db import operations
from src.exceptions.domain import (
    AgentAtCapacityError,
    InvalidAssigneeError,
    TicketStatusConflictError,
)
from src.services import tickets as tickets_service


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
        password="hash",
        updated_at=now,
        created_at=now,
        deleted_at=None,
        user_status=constants.UserStatus.ACTIVE,
    )


def _profile(
    user_id: str,
    department_id: str,
    now: datetime,
    *,
    capacity: int = 5,
) -> db_models.AgentProfile:
    return db_models.AgentProfile(
        user_id=user_id,
        availability_status=constants.AvailabilityStatus.AVAILABLE,
        availability_reason=None,
        availability_note=None,
        unavailable_until=None,
        max_active_tickets=capacity,
        last_assigned_at=None,
        department_id=department_id,
        created_at=now,
        updated_at=now,
        skills=[],
    )


def _ticket(
    ticket_id: str,
    now: datetime,
    *,
    department_id: str = "support",
    assigned_agent_id: str | None = None,
    status: constants.Status = constants.Status.NEW,
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


def _seed(
    engine,
    *,
    ticket_assigned_agent_id: str | None = None,
    ticket_status: constants.Status = constants.Status.NEW,
    agent1_capacity: int = 5,
) -> datetime:
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _department("support", now),
                _department("billing", now),
                _user("customer", constants.Role.USER, now),
                _user("agent1", constants.Role.AGENT, now),
                _user("agent2", constants.Role.AGENT, now),
                _user("billing-agent", constants.Role.AGENT, now),
                _user("manager", constants.Role.MANAGER, now),
            ]
        )
        session.flush()
        session.add_all(
            [
                _profile("agent1", "support", now, capacity=agent1_capacity),
                _profile("agent2", "support", now),
                _profile("billing-agent", "billing", now),
            ]
        )
        session.flush()
        session.add(
            _ticket(
                "ticket",
                now,
                department_id="support",
                assigned_agent_id=ticket_assigned_agent_id,
                status=ticket_status,
            )
        )
    return now


def _ticket_events(engine, ticket_id: str):
    with Session(engine) as session:
        return list(
            session.scalars(
                select(db_models.Event)
                .where(db_models.Event.entity_id == ticket_id)
                .order_by(db_models.Event.created_at)
            )
        )


def _run_stale_agent_race(engine, monkeypatch) -> tuple[Exception, object]:
    """Force: agent reads, manager reassigns, then the stale agent write runs."""
    _seed(
        engine,
        ticket_assigned_agent_id="agent1",
        ticket_status=constants.Status.IN_PROGRESS,
    )
    agent = operations.get_user("agent1")
    manager = operations.get_user("manager")

    agent_read = threading.Event()
    manager_committed = threading.Event()
    original_update = operations.update_ticket

    def delayed_update(ticket_id, new_info, event_data=None, expected=None):
        agent_read.set()
        assert manager_committed.wait(timeout=15), "manager never committed"
        return original_update(ticket_id, new_info, event_data, expected)

    monkeypatch.setattr(operations, "update_ticket", delayed_update)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            tickets_service.update_ticket,
            "ticket",
            models.TicketUpdate(status=constants.Status.RESOLVED),
            agent,
        )
        assert agent_read.wait(timeout=15), "agent never reached the write"
        tickets_service.assign_ticket("ticket", "agent2", manager)
        manager_committed.set()
        error = future.exception(timeout=15)

    stored = operations.get_ticket("ticket")
    return error, stored


def test_stale_agent_update_loses_to_concurrent_reassignment(
    mutation_engine,
    monkeypatch,
):
    error, stored = _run_stale_agent_race(mutation_engine, monkeypatch)

    assert isinstance(error, TicketStatusConflictError), repr(error)
    assert error.code == "ticket_state_conflict"
    assert stored.assigned_agent_id == "agent2"
    assert stored.status is constants.Status.OPEN


def test_contended_reassignment_audit_matches_committed_state(
    mutation_engine,
    monkeypatch,
):
    error, stored = _run_stale_agent_race(mutation_engine, monkeypatch)
    assert isinstance(error, TicketStatusConflictError)

    events = _ticket_events(mutation_engine, "ticket")
    assert len(events) == 1, "the rejected stale write must not persist an event"
    event = events[0]
    assert event.event_type is constants.EventType.TICKET_REASSIGNED

    committed = json.loads(event.new_value)
    assert committed["assigned_agent_id"] == stored.assigned_agent_id == "agent2"
    assert committed["status"] == stored.status.value == constants.Status.OPEN.value
    old_value = json.loads(event.old_value)
    assert old_value["assigned_agent_id"] == "agent1"


def test_delete_and_assign_overlap_never_activates_deleted_ticket(
    mutation_engine,
    monkeypatch,
):
    engine = mutation_engine
    _seed(engine)
    manager = operations.get_user("manager")

    assign_started = threading.Event()
    delete_committed = threading.Event()
    original_assign = operations.assign_ticket

    def delayed_assign(ticket_id, agent_id, event_data=None, expected=None):
        assign_started.set()
        assert delete_committed.wait(timeout=15), "delete never committed"
        return original_assign(ticket_id, agent_id, event_data, expected)

    monkeypatch.setattr(operations, "assign_ticket", delayed_assign)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            tickets_service.assign_ticket,
            "ticket",
            "agent1",
            manager,
        )
        assert assign_started.wait(timeout=15), "assign never reached the write"
        now = datetime.now(timezone.utc)
        operations.delete_ticket(
            "ticket",
            {"deleted_at": now, "updated_at": now},
        )
        delete_committed.set()
        error = future.exception(timeout=15)

    assert isinstance(error, TicketStatusConflictError), repr(error)
    stored = operations.get_ticket("ticket")
    assert stored.deleted_at is not None
    assert stored.assigned_agent_id is None
    assert stored.status is constants.Status.NEW


def test_combined_department_and_assignee_valid_combined_state(
    mutation_engine,
):
    engine = mutation_engine
    _seed(engine)
    manager = operations.get_user("manager")

    result = tickets_service.update_ticket(
        "ticket",
        models.TicketUpdate(
            department_id="billing",
            assigned_agent_id="billing-agent",
        ),
        manager,
    )

    assert result.department_id == "billing"
    assert result.assigned_agent_id == "billing-agent"
    assert result.status is constants.Status.OPEN
    stored = operations.get_ticket("ticket")
    assert stored.department_id == "billing"
    assert stored.assigned_agent_id == "billing-agent"
    assert stored.status is constants.Status.OPEN


def test_combined_department_and_assignee_mismatch_leaves_no_partial_update(
    mutation_engine,
):
    engine = mutation_engine
    _seed(engine)
    manager = operations.get_user("manager")

    with pytest.raises(InvalidAssigneeError) as exc_info:
        tickets_service.update_ticket(
            "ticket",
            models.TicketUpdate(
                department_id="billing",
                assigned_agent_id="agent1",
            ),
            manager,
        )
    assert exc_info.value.code == "assignee_department_mismatch"

    stored = operations.get_ticket("ticket")
    assert stored.department_id == "support"
    assert stored.assigned_agent_id is None
    assert stored.status is constants.Status.NEW
    assert _ticket_events(engine, "ticket") == []


def test_concurrent_claims_hold_capacity_limit_of_one(mutation_engine):
    engine = mutation_engine
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _department("support", now),
                _user("customer", constants.Role.USER, now),
                _user("agent1", constants.Role.AGENT, now),
            ]
        )
        session.flush()
        session.add(_profile("agent1", "support", now, capacity=1))
        session.flush()
        session.add_all([_ticket("claim-1", now), _ticket("claim-2", now)])

    barrier = threading.Barrier(2)

    def claim(ticket_id: str):
        barrier.wait(timeout=15)
        return operations.claim_ticket(ticket_id, "agent1", None)

    successes = []
    capacity_errors = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(claim, ticket_id)
            for ticket_id in ("claim-1", "claim-2")
        ]
        for future in futures:
            try:
                successes.append(future.result(timeout=15))
            except AgentAtCapacityError:
                capacity_errors.append(future.exception())

    assert len(successes) == 1, successes
    assert len(capacity_errors) == 1
    with Session(engine) as session:
        active = session.scalar(
            select(func.count())
            .select_from(db_models.Ticket)
            .where(
                db_models.Ticket.assigned_agent_id == "agent1",
                db_models.Ticket.deleted_at.is_(None),
                db_models.Ticket.status.in_(operations.ACTIVE_TICKET_STATUSES),
            )
        )
    assert active == 1
