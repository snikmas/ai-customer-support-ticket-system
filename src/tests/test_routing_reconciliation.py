from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src import constants
from src.db import models as db_models
from src.db import operations
from src.jobs import cron as routing_cron
from src.jobs import service as jobs_service
from src.models import TicketUpdate, UserUpdate
from src.services import tickets as tickets_service
from src.services import users as users_service


def _user(
    user_id: str,
    role: constants.Role,
    now: datetime,
    *,
    status: constants.UserStatus = constants.UserStatus.ACTIVE,
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
        user_status=status,
    )


def _ticket(
    ticket_id: str,
    creator_id: str,
    created_at: datetime,
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
        creator_user_id=creator_id,
        status=status,
        priority=constants.Priority.NORMAL,
        updated_at=created_at,
        created_at=created_at,
        deleted_at=deleted_at,
    )


def _profile(
    user_id: str,
    now: datetime,
    *,
    availability: constants.AvailabilityStatus,
    capacity: int,
) -> db_models.AgentProfile:
    return db_models.AgentProfile(
        user_id=user_id,
        availability_status=availability,
        availability_reason=None,
        availability_note=None,
        unavailable_until=None,
        max_active_tickets=capacity,
        last_assigned_at=None,
        department_id="support",
        created_at=now,
        updated_at=now,
    )


def _database(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'routing-reconciliation.db'}"
    )
    db_models.Base.metadata.create_all(engine)
    monkeypatch.setattr(operations, "engine", engine)
    return engine


def test_waiting_ticket_query_is_oldest_first_deterministic_and_bounded(
    monkeypatch,
    tmp_path,
):
    engine = _database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    tie_time = now - timedelta(hours=1)

    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _user("customer", constants.Role.USER, now),
                _user("agent", constants.Role.AGENT, now),
            ]
        )
        session.add_all(
            [
                _ticket("oldest", "customer", now - timedelta(hours=2)),
                _ticket("tie-b", "customer", tie_time),
                _ticket("tie-a", "customer", tie_time),
                _ticket("newest", "customer", now),
                _ticket(
                    "deleted",
                    "customer",
                    now - timedelta(days=1),
                    deleted_at=now,
                ),
                _ticket(
                    "already-assigned",
                    "customer",
                    now - timedelta(days=1),
                    assigned_agent_id="agent",
                ),
                _ticket(
                    "already-open",
                    "customer",
                    now - timedelta(days=1),
                    status=constants.Status.OPEN,
                ),
            ]
        )

    assert operations.get_waiting_ticket_ids(3) == [
        "oldest",
        "tie-a",
        "tie-b",
    ]


def test_dispatcher_enqueues_each_selected_ticket_independently(monkeypatch):
    attempted = []
    monkeypatch.setattr(
        jobs_service,
        "get_waiting_ticket_ids",
        lambda batch_size: ["ticket-1", "ticket-2", "ticket-3"][:batch_size],
    )

    def fake_enqueue(ticket_id):
        attempted.append(ticket_id)
        if ticket_id == "ticket-2":
            raise ConnectionError("Redis unavailable")
        return SimpleNamespace(id=f"route-ticket:{ticket_id}")

    monkeypatch.setattr(
        jobs_service,
        "enqueue_ticket_routing_job",
        fake_enqueue,
    )

    result = jobs_service.route_waiting_tickets(batch_size=3)

    assert attempted == ["ticket-1", "ticket-2", "ticket-3"]
    assert result == {
        "selected_count": 3,
        "enqueued_count": 2,
        "failed_count": 1,
        "enqueued_ticket_ids": ["ticket-1", "ticket-3"],
        "failed_ticket_ids": ["ticket-2"],
    }


def test_later_reconciliation_recovers_a_previously_unassigned_ticket(
    monkeypatch,
):
    attempts = 0
    enqueued = []
    monkeypatch.setattr(
        jobs_service,
        "get_waiting_ticket_ids",
        lambda _batch_size: ["waiting-ticket"],
    )

    def flaky_enqueue(ticket_id):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("first Redis attempt failed")
        enqueued.append(ticket_id)
        return SimpleNamespace(id=f"route-ticket:{ticket_id}")

    monkeypatch.setattr(
        jobs_service,
        "enqueue_ticket_routing_job",
        flaky_enqueue,
    )

    first = jobs_service.route_waiting_tickets(batch_size=1)
    second = jobs_service.route_waiting_tickets(batch_size=1)

    assert first["failed_ticket_ids"] == ["waiting-ticket"]
    assert second["enqueued_ticket_ids"] == ["waiting-ticket"]
    assert enqueued == ["waiting-ticket"]


def test_periodic_reconciliation_uses_configured_bounded_batch():
    schedule = routing_cron.ROUTING_RECONCILIATION_SCHEDULE

    assert schedule["func"] is jobs_service.route_waiting_tickets
    assert schedule["queue_name"] == "ticket_routing"
    assert schedule["interval"] > 0
    assert schedule["kwargs"]["batch_size"] > 0


def test_agent_capacity_events_trigger_dispatch_but_promotion_does_not(
    monkeypatch,
    tmp_path,
):
    engine = _database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _user("admin", constants.Role.ADMIN, now),
                _user("agent", constants.Role.AGENT, now),
                _user("future-agent", constants.Role.USER, now),
            ]
        )
        session.add(
            _profile(
                "agent",
                now,
                availability=constants.AvailabilityStatus.OFFLINE,
                capacity=1,
            )
        )

    dispatched = []
    monkeypatch.setattr(
        users_service,
        "dispatch_waiting_tickets_after_capacity_event",
        lambda event_name, entity_id: dispatched.append((event_name, entity_id)),
    )
    admin = SimpleNamespace(id="admin")
    agent = SimpleNamespace(id="agent")

    users_service.update_agent_availability(
        "agent",
        users_service.api_models.AgentAvailabilityUpdate(
            availability_status=constants.AvailabilityStatus.AVAILABLE,
        ),
        agent,
    )
    users_service.update_agent_profile_settings(
        "agent",
        users_service.api_models.AgentProfileManagementUpdate(
            max_active_tickets=2,
        ),
        admin,
    )
    users_service.update_user(
        "future-agent",
        UserUpdate(role=constants.Role.AGENT),
        admin,
    )

    assert dispatched == [
        ("agent_became_available", "agent"),
        ("agent_capacity_increased", "agent"),
    ]


def test_configured_agent_becoming_active_triggers_dispatch(
    monkeypatch,
    tmp_path,
):
    engine = _database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _user("admin", constants.Role.ADMIN, now),
                _user(
                    "agent",
                    constants.Role.AGENT,
                    now,
                    status=constants.UserStatus.BANNED,
                ),
            ]
        )
        session.add(
            _profile(
                "agent",
                now,
                availability=constants.AvailabilityStatus.AVAILABLE,
                capacity=1,
            )
        )

    dispatched = []
    monkeypatch.setattr(
        users_service,
        "dispatch_waiting_tickets_after_capacity_event",
        lambda event_name, entity_id: dispatched.append((event_name, entity_id)),
    )

    users_service.update_user(
        "agent",
        UserUpdate(user_status=constants.UserStatus.ACTIVE),
        SimpleNamespace(id="admin"),
    )

    assert dispatched == [("agent_became_eligible", "agent")]


def test_ticket_leaving_active_workload_triggers_dispatch(
    monkeypatch,
    make_ticket,
    make_user,
):
    ticket = make_ticket(
        id="active-ticket",
        assigned_agent_id="agent",
        status=constants.Status.IN_PROGRESS,
        tags=[constants.Tag.API_KEY],
    )
    requester = make_user(id="agent", role=constants.Role.AGENT)
    monkeypatch.setattr(
        tickets_service.operations,
        "get_ticket",
        lambda _ticket_id: ticket,
    )

    def fake_update(_ticket_id, new_info, _event):
        for field, value in new_info.items():
            setattr(ticket, field, value)
        return ticket

    monkeypatch.setattr(
        tickets_service.operations,
        "update_ticket",
        fake_update,
    )
    monkeypatch.setattr(
        tickets_service,
        "delete_cached_ticket",
        lambda _ticket_id: True,
    )
    dispatched = []
    monkeypatch.setattr(
        tickets_service,
        "dispatch_waiting_tickets_after_capacity_event",
        lambda event_name, entity_id: dispatched.append((event_name, entity_id)),
    )

    tickets_service.update_ticket(
        ticket.id,
        TicketUpdate(status=constants.Status.RESOLVED),
        requester,
    )

    assert dispatched == [
        ("ticket_left_active_workload", "active-ticket"),
    ]
