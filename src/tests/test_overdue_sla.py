from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src import constants, models
from src.db import models as db_models
from src.db import operations
from src.db.migrations import migrate_event_actor_contract
from src.jobs import cron as jobs_cron
from src.jobs import tasks as job_tasks
from src.services import tickets as ticket_service


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def _user(user_id: str, role: constants.Role) -> db_models.User:
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
        updated_at=NOW,
        created_at=NOW,
        deleted_at=None,
        user_status=constants.UserStatus.ACTIVE,
    )


def _ticket(
    ticket_id: str,
    creator_id: str,
    due_at: datetime | None,
    *,
    priority: constants.Priority = constants.Priority.NORMAL,
) -> db_models.Ticket:
    return db_models.Ticket(
        id=ticket_id,
        title="SLA ticket",
        description="Deadline behavior",
        category=constants.Category.ACCOUNT_ACCESS,
        tags=None,
        department_id="support",
        assigned_agent_id=None,
        creator_user_id=creator_id,
        status=constants.Status.NEW,
        priority=priority,
        updated_at=NOW,
        created_at=NOW,
        due_at=due_at,
        deleted_at=None,
    )


def _database(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'overdue.db'}",
        connect_args={"timeout": 10},
    )
    db_models.Base.metadata.create_all(engine)
    monkeypatch.setattr(operations, "engine", engine)
    with Session(engine) as session, session.begin():
        session.add(
            db_models.Department(
                id="support",
                name="Support",
                normalized_name="support",
                description=None,
                created_at=NOW,
                updated_at=NOW,
                deleted_at=None,
            )
        )
        session.add_all([
            _user("customer-a", constants.Role.USER),
            _user("customer-b", constants.Role.USER),
            _user("manager", constants.Role.MANAGER),
        ])
    return engine


@pytest.mark.parametrize(
    ("priority", "multiplier"),
    [
        (constants.Priority.CRITICAL, 0.25),
        (constants.Priority.HIGH, 0.5),
        (constants.Priority.NORMAL, 1.0),
        (constants.Priority.LOW, 2.0),
    ],
)
def test_sla_policy_applies_every_priority_multiplier(priority, multiplier):
    due_at = constants.calculate_sla_due_at(constants.Status.OPEN, NOW, priority)
    assert due_at == NOW + timedelta(hours=6 * multiplier)


def test_exact_deadline_is_not_overdue_until_time_moves_past_it():
    assert constants.is_ticket_overdue(NOW, NOW) is False
    assert constants.is_ticket_overdue(NOW, NOW + timedelta(microseconds=1)) is True
    assert constants.is_ticket_overdue(None, NOW) is False


def test_reprioritizing_ticket_recalculates_deadline(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session, session.begin():
        session.add(_ticket("ticket", "customer-a", NOW + timedelta(hours=2)))
    monkeypatch.setattr(constants, "utc_now", lambda: NOW)
    monkeypatch.setattr(ticket_service, "delete_cached_ticket", lambda *_: True)
    with Session(engine) as session:
        manager = session.get(db_models.User, "manager")

    result = ticket_service.update_ticket(
        "ticket",
        models.TicketUpdate(priority=constants.Priority.CRITICAL),
        manager,
    )
    assert result.priority is constants.Priority.CRITICAL
    assert result.due_at == NOW + timedelta(minutes=30)


def test_overdue_filter_is_bounded_visible_and_read_only(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session, session.begin():
        session.add_all([
            _ticket("mine-overdue", "customer-a", NOW - timedelta(seconds=1)),
            _ticket("other-overdue", "customer-b", NOW - timedelta(seconds=1)),
            _ticket("mine-boundary", "customer-a", NOW),
        ])
    monkeypatch.setattr(constants, "utc_now", lambda: NOW)
    with Session(engine) as session:
        customer = session.get(db_models.User, "customer-a")
        manager = session.get(db_models.User, "manager")
        events_before = session.scalar(select(func.count()).select_from(db_models.Event))

    customer_results = ticket_service.get_all_tickets(
        customer,
        1,
        0,
        "created_at",
        "desc",
        None,
        None,
        True,
    )
    manager_results = ticket_service.get_all_tickets(
        manager,
        100,
        0,
        "created_at",
        "desc",
        None,
        None,
        True,
    )
    assert [ticket.id for ticket in customer_results] == ["mine-overdue"]
    assert all(ticket.is_overdue for ticket in manager_results)
    assert {ticket.id for ticket in manager_results} == {"mine-overdue", "other-overdue"}
    with Session(engine) as session:
        events_after = session.scalar(select(func.count()).select_from(db_models.Event))
    assert events_after == events_before == 0


def test_overdue_scanner_is_idempotent_and_system_authored(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session, session.begin():
        session.add_all([
            _ticket("overdue", "customer-a", NOW - timedelta(seconds=1)),
            _ticket("boundary", "customer-a", NOW),
            _ticket("future", "customer-a", NOW + timedelta(seconds=1)),
        ])

    assert operations.record_overdue_ticket_events(100, NOW) == ["overdue"]
    assert operations.record_overdue_ticket_events(100, NOW) == []
    with Session(engine) as session:
        event = session.scalar(select(db_models.Event))
    assert event.entity_id == "overdue"
    assert event.actor_type is constants.ActorType.SYSTEM
    assert event.actor_user_id is None
    assert event.idempotency_key == "ticket-overdue:overdue"

    with Session(engine) as session:
        customer = session.get(db_models.User, "customer-a")
    history = ticket_service.get_ticket_history("overdue", customer, 20, 0)
    overdue_event = next(
        item for item in history
        if item.event_type is constants.EventType.TICKET_OVERDUE
    )
    assert overdue_event.actor_type is constants.ActorType.SYSTEM
    assert overdue_event.actor_user_id is None
    assert overdue_event.new_value["is_overdue"] is True


def test_concurrent_overdue_scans_write_one_event(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session, session.begin():
        session.add(_ticket("overdue", "customer-a", NOW - timedelta(seconds=1)))
    barrier = Barrier(2)

    def scan():
        barrier.wait()
        return operations.record_overdue_ticket_events(100, NOW)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: scan(), range(2)))
    assert sorted(results, key=len) == [[], ["overdue"]]
    with Session(engine) as session:
        count = session.scalar(select(func.count()).select_from(db_models.Event))
    assert count == 1


def test_overdue_scanner_rolls_back_whole_batch_on_audit_failure(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session, session.begin():
        session.add_all([
            _ticket("first", "customer-a", NOW - timedelta(seconds=2)),
            _ticket("second", "customer-a", NOW - timedelta(seconds=1)),
        ])
    monkeypatch.setattr(operations, "generate_id", lambda: "duplicate")

    with pytest.raises(IntegrityError):
        operations.record_overdue_ticket_events(100, NOW)
    with Session(engine) as session:
        count = session.scalar(select(func.count()).select_from(db_models.Event))
    assert count == 0


def test_event_actor_migration_preserves_human_events_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy-events.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO users (id) VALUES ('human')")
        connection.exec_driver_sql(
            "CREATE TABLE events ("
            "id VARCHAR(36) PRIMARY KEY, entity_type VARCHAR(32) NOT NULL, "
            "entity_id VARCHAR(36), actor_user_id VARCHAR(36) NOT NULL, "
            "event_type VARCHAR(40) NOT NULL, old_value TEXT, batch_id VARCHAR(36), "
            "new_value TEXT NOT NULL, metadata VARCHAR(200), created_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO events VALUES "
            "('event', 'TICKET', 'ticket', 'human', 'TICKET_CREATED', NULL, NULL, '{}', NULL, '2026-07-21')"
        )

    migrate_event_actor_contract(engine)
    migrate_event_actor_contract(engine)

    columns = {column["name"]: column for column in inspect(engine).get_columns("events")}
    assert columns["actor_user_id"]["nullable"] is True
    assert "actor_type" in columns
    assert "idempotency_key" in columns
    with engine.connect() as connection:
        actor = connection.exec_driver_sql(
            "SELECT actor_type, actor_user_id FROM events"
        ).one()
    assert actor == ("HUMAN", "human")


def test_periodic_overdue_scan_uses_configured_bounded_batch():
    schedule = jobs_cron.OVERDUE_SCAN_SCHEDULE

    assert schedule["func"] is job_tasks.scan_overdue_tickets
    assert schedule["queue_name"] == "ticket_routing"
    assert schedule["interval"] > 0
    assert schedule["kwargs"]["batch_size"] > 0
