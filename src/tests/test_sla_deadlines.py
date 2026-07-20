import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from src import constants
from src.db import models as db_models
from src.db import operations
from src.db.migrations import add_ticket_due_at
from src.models import TicketCreate, TicketUpdate
from src.services import tickets as ticket_service


FIXED_NOW = datetime(
    2026,
    3,
    29,
    23,
    30,
    tzinfo=timezone(timedelta(hours=5, minutes=30)),
)
FIXED_UTC = FIXED_NOW.astimezone(timezone.utc)


@pytest.mark.parametrize(
    ("status", "hours"),
    [
        (constants.Status.NEW, 2),
        (constants.Status.OPEN, 6),
        (constants.Status.IN_PROGRESS, 12),
        (constants.Status.REOPENED, 4),
        (constants.Status.PENDING, None),
        (constants.Status.ON_HOLD, None),
        (constants.Status.RESOLVED, None),
        (constants.Status.CLOSED, None),
    ],
)
def test_calculate_sla_due_at_uses_fixed_aware_clock(status, hours):
    due_at = constants.calculate_sla_due_at(status, FIXED_NOW)

    if hours is None:
        assert due_at is None
    else:
        assert due_at == FIXED_UTC + timedelta(hours=hours)
        assert due_at.tzinfo is timezone.utc


def test_calculate_sla_due_at_rejects_naive_clock():
    with pytest.raises(ValueError, match="timezone-aware"):
        constants.calculate_sla_due_at(
            constants.Status.NEW,
            datetime(2026, 3, 29, 23, 30),
        )


def test_due_at_migration_is_idempotent_for_existing_sqlite_table(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE tickets (id VARCHAR(36) PRIMARY KEY)"
        )

    add_ticket_due_at(engine)
    add_ticket_due_at(engine)

    columns = {
        column["name"] for column in inspect(engine).get_columns("tickets")
    }
    assert columns == {"id", "due_at"}


def test_ticket_creation_sets_fixed_new_deadline(monkeypatch, make_user):
    requester = make_user()
    captured = {}
    monkeypatch.setattr(constants, "utc_now", lambda: FIXED_UTC)
    monkeypatch.setattr(
        ticket_service.operations,
        "create_ticket",
        lambda ticket, event: captured.update(event=event) or ticket,
    )
    monkeypatch.setattr(
        ticket_service,
        "enqueue_ticket_routing_job",
        lambda *_: None,
    )

    ticket = ticket_service.create_ticket(
        TicketCreate(
            title="SLA boundary",
            description="Check the initial stage deadline",
            category=constants.Category.ACCOUNT_ACCESS,
        ),
        requester,
    )

    assert ticket.due_at == FIXED_UTC + timedelta(hours=2)
    created_snapshot = json.loads(captured["event"].new_value)
    assert created_snapshot["due_at"] == ticket.due_at.isoformat()


@pytest.mark.parametrize(
    ("old_status", "new_status", "hours"),
    [
        (constants.Status.IN_PROGRESS, constants.Status.PENDING, None),
        (constants.Status.IN_PROGRESS, constants.Status.ON_HOLD, None),
        (constants.Status.IN_PROGRESS, constants.Status.RESOLVED, None),
        (constants.Status.PENDING, constants.Status.IN_PROGRESS, 12),
        (constants.Status.ON_HOLD, constants.Status.IN_PROGRESS, 12),
        (constants.Status.RESOLVED, constants.Status.CLOSED, None),
        (constants.Status.CLOSED, constants.Status.REOPENED, 4),
        (constants.Status.REOPENED, constants.Status.IN_PROGRESS, 12),
    ],
)
def test_status_transition_replaces_deadline_and_audits_old_and_new_values(
    monkeypatch,
    make_user,
    make_ticket,
    old_status,
    new_status,
    hours,
):
    requester = make_user(id="agent", role=constants.Role.AGENT)
    old_due_at = FIXED_UTC - timedelta(hours=1)
    ticket = make_ticket(
        assigned_agent_id=requester.id,
        status=old_status,
    )
    ticket.due_at = old_due_at
    captured = {}

    def fake_update(ticket_id, changes, event):
        captured.update(changes=changes.copy(), event=event)
        for field, value in changes.items():
            setattr(ticket, field, value)
        return ticket

    monkeypatch.setattr(constants, "utc_now", lambda: FIXED_UTC)
    monkeypatch.setattr(ticket_service.operations, "get_ticket", lambda *_: ticket)
    monkeypatch.setattr(ticket_service.operations, "update_ticket", fake_update)
    monkeypatch.setattr(ticket_service, "delete_cached_ticket", lambda *_: True)
    monkeypatch.setattr(
        ticket_service,
        "dispatch_waiting_tickets_after_capacity_event",
        lambda *_: None,
    )

    result = ticket_service.update_ticket(
        ticket.id,
        TicketUpdate(status=new_status),
        requester,
    )

    expected_due_at = (
        None
        if hours is None
        else FIXED_UTC + timedelta(hours=hours)
    )
    assert result.due_at == expected_due_at
    old_snapshot = json.loads(captured["event"].old_value)
    new_snapshot = json.loads(captured["event"].new_value)
    assert old_snapshot["due_at"] == old_due_at.isoformat()
    assert new_snapshot["due_at"] == (
        None if expected_due_at is None else expected_due_at.isoformat()
    )


def _db_user(user_id, role):
    return db_models.User(
        id=user_id,
        nickname=user_id,
        avatar_url=None,
        first_name="SLA",
        last_name="Test",
        phone=f"phone-{user_id}",
        email=f"{user_id}@example.com",
        role=role,
        password="hash",
        updated_at=FIXED_UTC,
        created_at=FIXED_UTC,
        deleted_at=None,
        user_status=constants.UserStatus.ACTIVE,
    )


def _db_ticket(status, due_at, assigned_agent_id=None):
    return db_models.Ticket(
        id="ticket",
        title="SLA ticket",
        description="SLA transition",
        category=constants.Category.ACCOUNT_ACCESS,
        tags=None,
        assigned_agent_id=assigned_agent_id,
        creator_user_id="customer",
        status=status,
        priority=constants.Priority.NORMAL,
        updated_at=FIXED_UTC,
        created_at=FIXED_UTC,
        due_at=due_at,
        deleted_at=None,
    )


def _sla_engine(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'sla.db'}",
        connect_args={"timeout": 10},
    )
    db_models.Base.metadata.create_all(engine)
    monkeypatch.setattr(operations, "engine", engine)
    monkeypatch.setattr(operations, "utc_now", lambda: FIXED_UTC)
    return engine


def test_automatic_assignment_sets_open_deadline_in_its_transaction(
    monkeypatch,
    tmp_path,
):
    engine = _sla_engine(monkeypatch, tmp_path)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _db_user("customer", constants.Role.USER),
                _db_user("agent", constants.Role.AGENT),
                db_models.AgentProfile(
                    user_id="agent",
                    availability_status=constants.AvailabilityStatus.AVAILABLE,
                    availability_reason=None,
                    availability_note=None,
                    unavailable_until=None,
                    max_active_tickets=1,
                    last_assigned_at=None,
                    department_id=None,
                    created_at=FIXED_UTC,
                    updated_at=FIXED_UTC,
                ),
                _db_ticket(
                    constants.Status.NEW,
                    FIXED_UTC + timedelta(hours=2),
                ),
            ]
        )

    result = operations.try_route_ticket("ticket")

    assert result.outcome is constants.TicketRoutingOutcome.ASSIGNED
    with Session(engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        event = session.scalar(select(db_models.Event))
        assert ticket.status is constants.Status.OPEN
        assert ticket.due_at == FIXED_UTC + timedelta(hours=6)
        assert ticket.due_at.tzinfo is timezone.utc
        assert json.loads(event.old_value)["due_at"] == (
            FIXED_UTC + timedelta(hours=2)
        ).isoformat()
        assert json.loads(event.new_value)["due_at"] == ticket.due_at.isoformat()


def test_start_work_sets_in_progress_deadline_and_audits_it_atomically(
    monkeypatch,
    tmp_path,
):
    engine = _sla_engine(monkeypatch, tmp_path)
    old_due_at = FIXED_UTC + timedelta(hours=6)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _db_user("customer", constants.Role.USER),
                _db_user("agent", constants.Role.AGENT),
                _db_ticket(
                    constants.Status.OPEN,
                    old_due_at,
                    assigned_agent_id="agent",
                ),
            ]
        )

    result = operations.start_ticket_work("ticket", "agent")

    assert result.outcome is constants.StartWorkOutcome.STARTED
    with Session(engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        event = session.scalar(select(db_models.Event))
        assert ticket.due_at == FIXED_UTC + timedelta(hours=12)
        assert json.loads(event.old_value)["due_at"] == old_due_at.isoformat()
        assert json.loads(event.new_value)["due_at"] == ticket.due_at.isoformat()
