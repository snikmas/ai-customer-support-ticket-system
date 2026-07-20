import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src import constants
from src.db import models as db_models
from src.db import operations


def _user(
    user_id: str,
    role: constants.Role,
    now: datetime,
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
    capacity: int = 3,
    last_assigned_at: datetime | None = None,
) -> db_models.AgentProfile:
    return db_models.AgentProfile(
        user_id=user_id,
        availability_status=constants.AvailabilityStatus.AVAILABLE,
        availability_reason=None,
        availability_note=None,
        unavailable_until=None,
        max_active_tickets=capacity,
        last_assigned_at=last_assigned_at,
        department_id="support",
        created_at=now,
        updated_at=now,
    )


def _ticket(
    ticket_id: str,
    now: datetime,
    *,
    status: constants.Status = constants.Status.NEW,
    assigned_agent_id: str | None = None,
    deleted_at: datetime | None = None,
) -> db_models.Ticket:
    return db_models.Ticket(
        id=ticket_id,
        title="Ticket",
        description="Description",
        category=constants.Category.ACCOUNT_ACCESS,
        tags=None,
        assigned_agent_id=assigned_agent_id,
        creator_user_id="customer",
        status=status,
        priority=constants.Priority.NORMAL,
        updated_at=now,
        created_at=now,
        deleted_at=deleted_at,
    )


def _prepare_database(monkeypatch, tmp_path):
    from sqlalchemy import create_engine

    test_engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'ticket-routing.db'}",
        connect_args={"timeout": 10},
    )
    db_models.Base.metadata.create_all(test_engine)
    monkeypatch.setattr(operations, "engine", test_engine)
    return test_engine


def _seed(
    test_engine,
    now: datetime,
    *,
    ticket: db_models.Ticket,
    profiles: list[db_models.AgentProfile],
) -> None:
    with Session(test_engine) as session, session.begin():
        session.add(_user("customer", constants.Role.USER, now))
        session.add_all(
            _user(profile.user_id, constants.Role.AGENT, now)
            for profile in profiles
        )
        session.add_all(profiles)
        session.add(ticket)


def test_try_route_ticket_assigns_and_audits_atomically(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    never_assigned = _profile("agent-a", now)
    previous_assignment = now
    previously_assigned = _profile(
        "agent-b",
        now,
        last_assigned_at=previous_assignment,
    )
    _seed(
        test_engine,
        now,
        ticket=_ticket("ticket", now),
        profiles=[never_assigned, previously_assigned],
    )
    with Session(test_engine) as session:
        stored_previous_assignment = session.get(
            db_models.AgentProfile,
            "agent-b",
        ).last_assigned_at

    result = operations.try_route_ticket("ticket")

    assert result.outcome is constants.TicketRoutingOutcome.ASSIGNED
    assert result.ticket_id == "ticket"
    assert result.assigned_agent_id == "agent-a"
    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        agent_a = session.get(db_models.AgentProfile, "agent-a")
        agent_b = session.get(db_models.AgentProfile, "agent-b")
        event = session.scalar(select(db_models.Event))

        assert ticket.assigned_agent_id == "agent-a"
        assert ticket.status is constants.Status.OPEN
        assert agent_a.last_assigned_at is not None
        assert agent_b.last_assigned_at == stored_previous_assignment
        assert event.entity_id == "ticket"
        assert event.actor_user_id == "customer"
        assert event.event_type is constants.EventType.TICKET_ASSIGNED
        assert event.metadata_ == "source=automatic_router"
        assert json.loads(event.old_value) == {
            "status": constants.Status.NEW.value,
            "assigned_agent_id": None,
        }
        assert json.loads(event.new_value) == {
            "status": constants.Status.OPEN.value,
            "assigned_agent_id": "agent-a",
        }


def test_try_route_ticket_leaves_ticket_when_no_agent_is_eligible(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed(
        test_engine,
        now,
        ticket=_ticket("ticket", now),
        profiles=[_profile("agent-at-capacity", now, capacity=0)],
    )

    result = operations.try_route_ticket("ticket")

    assert result.outcome is constants.TicketRoutingOutcome.NO_ELIGIBLE_AGENT
    assert result.assigned_agent_id is None
    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        event_count = session.scalar(
            select(func.count(db_models.Event.id))
        )
        assert ticket.status is constants.Status.NEW
        assert ticket.assigned_agent_id is None
        assert event_count == 0


def test_try_route_ticket_rolls_back_assignment_when_audit_insert_fails(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed(
        test_engine,
        now,
        ticket=_ticket("ticket", now),
        profiles=[_profile("agent", now)],
    )
    with Session(test_engine) as session, session.begin():
        session.add(
            db_models.Event(
                id="duplicate-event",
                entity_type=constants.EntityType.TICKET,
                entity_id="ticket",
                actor_user_id="customer",
                event_type=constants.EventType.TICKET_CREATED,
                old_value=None,
                new_value="{}",
                metadata_=None,
                created_at=now,
            )
        )
    monkeypatch.setattr(
        operations,
        "generate_id",
        lambda: "duplicate-event",
    )

    with pytest.raises(IntegrityError):
        operations.try_route_ticket("ticket")

    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        profile = session.get(db_models.AgentProfile, "agent")
        event_count = session.scalar(
            select(func.count(db_models.Event.id))
        )
        assert ticket.status is constants.Status.NEW
        assert ticket.assigned_agent_id is None
        assert profile.last_assigned_at is None
        assert event_count == 1


@pytest.mark.parametrize(
    ("status", "deleted"),
    [
        (constants.Status.OPEN, False),
        (constants.Status.NEW, True),
    ],
)
def test_try_route_ticket_rejects_deleted_or_non_new_ticket(
    monkeypatch,
    tmp_path,
    status,
    deleted,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    deleted_at = now if deleted else None
    _seed(
        test_engine,
        now,
        ticket=_ticket(
            "ticket",
            now,
            status=status,
            deleted_at=deleted_at,
        ),
        profiles=[_profile("agent", now)],
    )

    result = operations.try_route_ticket("ticket")

    assert result.outcome is constants.TicketRoutingOutcome.TICKET_NOT_ROUTABLE
    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        profile = session.get(db_models.AgentProfile, "agent")
        assert ticket.status is status
        assert ticket.assigned_agent_id is None
        assert (ticket.deleted_at is not None) is deleted
        assert profile.last_assigned_at is None


def test_try_route_ticket_repeated_call_is_a_no_op(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed(
        test_engine,
        now,
        ticket=_ticket("ticket", now),
        profiles=[_profile("agent-a", now), _profile("agent-b", now)],
    )

    first = operations.try_route_ticket("ticket")
    second = operations.try_route_ticket("ticket")

    assert first.outcome is constants.TicketRoutingOutcome.ASSIGNED
    assert second.outcome is constants.TicketRoutingOutcome.TICKET_NOT_ROUTABLE
    assert second.assigned_agent_id is None
    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        event_count = session.scalar(
            select(func.count(db_models.Event.id))
        )
        assert ticket.assigned_agent_id == first.assigned_agent_id
        assert event_count == 1


def test_competing_routing_attempts_assign_ticket_only_once(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed(
        test_engine,
        now,
        ticket=_ticket("ticket", now),
        profiles=[_profile("agent-a", now), _profile("agent-b", now)],
    )
    start_together = Barrier(2)

    def route():
        start_together.wait()
        return operations.try_route_ticket("ticket")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: route(), range(2)))

    assert sorted(result.outcome.value for result in results) == [
        constants.TicketRoutingOutcome.ASSIGNED.value,
        constants.TicketRoutingOutcome.TICKET_NOT_ROUTABLE.value,
    ]
    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        event_count = session.scalar(
            select(func.count(db_models.Event.id))
        )
        timestamp_count = session.scalar(
            select(func.count(db_models.AgentProfile.user_id)).where(
                db_models.AgentProfile.last_assigned_at.is_not(None)
            )
        )
        assert ticket.status is constants.Status.OPEN
        assert ticket.assigned_agent_id in {"agent-a", "agent-b"}
        assert event_count == 1
        assert timestamp_count == 1
