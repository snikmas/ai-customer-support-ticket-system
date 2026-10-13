"""Phase G regressions: bounded, fair routing reconciliation.

The old scanner always returned the same oldest page, so a ticket behind more
than one batch of unassignable tickets was never selected. These tests assert
the desired behavior: least-recently-attempted (never-attempted first) rotation
with a deterministic tiebreaker, a finite recovery bound, and durable progress
that does not reset when new tickets arrive or a scanner restarts.

Each test fails against the unfair scanner because it keeps selecting the same
oldest unassignable page, and passes once the scan rotates.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src import constants
from src.db import models as db_models
from src.db import operations
from src.jobs import service as jobs_service


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
    capacity: int = 10,
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
    created_at: datetime,
    department_id: str,
) -> db_models.Ticket:
    return db_models.Ticket(
        id=ticket_id,
        title="Ticket",
        description="Description",
        category=constants.Category.ACCOUNT_ACCESS,
        tags=None,
        department_id=department_id,
        assigned_agent_id=None,
        creator_user_id="customer",
        status=constants.Status.NEW,
        priority=constants.Priority.NORMAL,
        updated_at=created_at,
        created_at=created_at,
        due_at=None,
        deleted_at=None,
    )


def _sqlite_engine(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'routing-fairness.db'}",
        connect_args={"timeout": 15},
    )
    db_models.Base.metadata.create_all(engine)
    return engine


def _seed(
    engine,
    now: datetime,
    *,
    unassignable_count: int,
    include_assignable: bool = False,
    support_capacity: int = 10,
) -> None:
    """Seed an unassignable billing backlog followed by an assignable ticket.

    Billing has no agent, so every billing ticket returns NO_ELIGIBLE_AGENT and
    stays waiting. Support has one available agent, so the support ticket is the
    one the fair scanner is expected to reach.
    """
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _department("support", now),
                _department("billing", now),
                _user("customer", constants.Role.USER, now),
                _user("support-agent", constants.Role.AGENT, now),
            ]
        )
        session.flush()
        session.add(
            _profile(
                "support-agent",
                "support",
                now,
                capacity=support_capacity,
            )
        )
        session.flush()
        for index in range(unassignable_count):
            session.add(
                _ticket(
                    f"blocked-{index:03d}",
                    now - timedelta(minutes=unassignable_count - index),
                    "billing",
                )
            )
        if include_assignable:
            session.add(_ticket("support-ticket", now, "support"))


def _recording_router(seen):
    def route(ticket_id):
        seen.append(ticket_id)
        operations.try_route_ticket(ticket_id)
        return SimpleNamespace(id=f"route-ticket-{ticket_id}")

    return route


def test_unassignable_backlog_does_not_starve_a_later_assignable_ticket(
    monkeypatch,
    tmp_path,
):
    engine = _sqlite_engine(tmp_path)
    monkeypatch.setattr(operations, "engine", engine)
    now = datetime.now(timezone.utc)
    _seed(engine, now, unassignable_count=5, include_assignable=True)

    seen = []
    monkeypatch.setattr(
        jobs_service,
        "enqueue_ticket_routing_job",
        _recording_router(seen),
    )

    # Six waiting tickets, batch of two: a fair scan reaches the last ticket in
    # ceil(6 / 2) = 3 passes.
    for _ in range(3):
        jobs_service.route_waiting_tickets(batch_size=2)

    assert "support-ticket" in seen
    assert operations.get_ticket("support-ticket").assigned_agent_id == "support-agent"


def test_scan_rotates_the_page_and_wraps_instead_of_repeating_it(
    monkeypatch,
    tmp_path,
):
    engine = _sqlite_engine(tmp_path)
    monkeypatch.setattr(operations, "engine", engine)
    now = datetime.now(timezone.utc)
    _seed(engine, now, unassignable_count=4, include_assignable=False)

    pages = []
    current_pass = []

    def route(ticket_id):
        current_pass.append(ticket_id)
        return SimpleNamespace(id=f"route-ticket-{ticket_id}")

    monkeypatch.setattr(jobs_service, "enqueue_ticket_routing_job", route)

    for _ in range(3):
        current_pass = []
        jobs_service.route_waiting_tickets(batch_size=2)
        pages.append(set(current_pass))

    # Pass 1 and pass 2 must differ: progress is durable, so the scanner does
    # not re-fetch the same oldest page. Pass 3 wraps back to the first page.
    assert pages[0] and pages[1]
    assert pages[0].isdisjoint(pages[1])
    assert pages[2] == pages[0]


def test_new_arrivals_do_not_reset_progress_indefinitely(
    monkeypatch,
    tmp_path,
):
    engine = _sqlite_engine(tmp_path)
    monkeypatch.setattr(operations, "engine", engine)
    now = datetime.now(timezone.utc)
    _seed(engine, now, unassignable_count=4, include_assignable=True)

    seen = []
    monkeypatch.setattr(
        jobs_service,
        "enqueue_ticket_routing_job",
        _recording_router(seen),
    )

    jobs_service.route_waiting_tickets(batch_size=2)

    # A brand-new unassignable arrival lands with no attempt time. It must not
    # push the already-waiting assignable ticket out of the finite bound.
    with Session(engine) as session, session.begin():
        session.add(_ticket("late-arrival", now + timedelta(seconds=1), "billing"))

    for _ in range(2):
        jobs_service.route_waiting_tickets(batch_size=2)

    assert "support-ticket" in seen
    assert operations.get_ticket("support-ticket").assigned_agent_id == "support-agent"


def test_concurrent_scanners_do_not_duplicate_or_over_assign(
    mutation_engine,
    monkeypatch,
):
    engine = mutation_engine
    now = datetime.now(timezone.utc)
    _seed(
        engine,
        now,
        unassignable_count=4,
        include_assignable=True,
        support_capacity=1,
    )
    with Session(engine) as session, session.begin():
        session.add(_ticket("support-ticket-2", now + timedelta(seconds=1), "support"))

    def route(ticket_id):
        operations.try_route_ticket(ticket_id)
        return SimpleNamespace(id=f"route-ticket-{ticket_id}")

    monkeypatch.setattr(jobs_service, "enqueue_ticket_routing_job", route)

    start_together = Barrier(2)

    def scan():
        start_together.wait(timeout=15)
        for _ in range(4):
            jobs_service.route_waiting_tickets(batch_size=2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: scan(), range(2)))

    with Session(engine) as session:
        assigned = list(
            session.scalars(
                select(db_models.Ticket).where(
                    db_models.Ticket.assigned_agent_id.is_not(None)
                )
            )
        )
        events = list(
            session.scalars(
                select(db_models.Event).where(
                    db_models.Event.event_type == constants.EventType.TICKET_ASSIGNED
                )
            )
        )

    # Capacity is one; two scanners racing must still assign exactly one ticket
    # once, with exactly one audit event.
    assert len(assigned) == 1, [ticket.id for ticket in assigned]
    assert assigned[0].assigned_agent_id == "support-agent"
    assert len(events) == 1
