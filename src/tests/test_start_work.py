import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from main import app
from src import constants
from src.db import models as db_models
from src.db import operations
from src.exceptions.domain import (
    AuthorizationError,
    TicketStartWorkConflictError,
)
from src.routers import tickets as tickets_router
from src.services import tickets as tickets_service


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


def _ticket(
    ticket_id: str,
    now: datetime,
    *,
    assigned_agent_id: str | None = "agent-a",
    status: constants.Status = constants.Status.OPEN,
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
        f"sqlite+pysqlite:///{tmp_path / 'start-work.db'}",
        connect_args={"timeout": 10},
    )
    db_models.Base.metadata.create_all(test_engine)
    monkeypatch.setattr(operations, "engine", test_engine)
    return test_engine


def _seed(test_engine, ticket: db_models.Ticket, now: datetime) -> None:
    with Session(test_engine) as session, session.begin():
        session.add_all(
            [
                _user("customer", constants.Role.USER, now),
                _user("agent-a", constants.Role.AGENT, now),
                _user("agent-b", constants.Role.AGENT, now),
                ticket,
            ]
        )


def test_database_start_work_changes_status_and_audits_atomically(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed(test_engine, _ticket("ticket", now), now)

    result = operations.start_ticket_work("ticket", "agent-a")

    assert result.outcome is constants.StartWorkOutcome.STARTED
    assert result.ticket.status is constants.Status.IN_PROGRESS
    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        event = session.scalar(select(db_models.Event))

        assert ticket.status is constants.Status.IN_PROGRESS
        assert event.entity_id == ticket.id
        assert event.actor_user_id == "agent-a"
        assert event.event_type is constants.EventType.TICKET_STATUS_CHANGED
        assert json.loads(event.old_value) == {
            "status": constants.Status.OPEN.value
        }
        assert json.loads(event.new_value) == {
            "status": constants.Status.IN_PROGRESS.value
        }


@pytest.mark.parametrize(
    ("ticket", "requester_id", "expected_outcome"),
    [
        (
            lambda now: _ticket("ticket", now, assigned_agent_id=None),
            "agent-a",
            constants.StartWorkOutcome.TICKET_UNASSIGNED,
        ),
        (
            lambda now: _ticket(
                "ticket",
                now,
                status=constants.Status.IN_PROGRESS,
            ),
            "agent-a",
            constants.StartWorkOutcome.TICKET_ALREADY_STARTED,
        ),
        (
            lambda now: _ticket(
                "ticket",
                now,
                status=constants.Status.PENDING,
            ),
            "agent-a",
            constants.StartWorkOutcome.TICKET_NOT_OPEN,
        ),
        (
            lambda now: _ticket("ticket", now, assigned_agent_id="agent-b"),
            "agent-a",
            constants.StartWorkOutcome.ASSIGNED_TO_ANOTHER_AGENT,
        ),
        (
            lambda now: _ticket("ticket", now, deleted_at=now),
            "agent-a",
            constants.StartWorkOutcome.TICKET_DELETED,
        ),
    ],
)
def test_database_start_work_rejects_ineligible_ticket_without_changes(
    monkeypatch,
    tmp_path,
    ticket,
    requester_id,
    expected_outcome,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    seeded_ticket = ticket(now)
    original_status = seeded_ticket.status
    _seed(test_engine, seeded_ticket, now)

    result = operations.start_ticket_work("ticket", requester_id)

    assert result.outcome is expected_outcome
    with Session(test_engine) as session:
        stored_ticket = session.get(db_models.Ticket, "ticket")
        event_count = session.scalar(
            select(func.count()).select_from(db_models.Event)
        )
        assert stored_ticket.status is original_status
        assert event_count == 0


def test_database_start_work_rolls_back_status_when_audit_fails(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed(test_engine, _ticket("ticket", now), now)
    with Session(test_engine) as session, session.begin():
        session.add(
            db_models.Event(
                id="duplicate-event",
                entity_type=constants.EntityType.TICKET,
                entity_id="ticket",
                actor_user_id="agent-a",
                event_type=constants.EventType.TICKET_CREATED,
                old_value=None,
                new_value="{}",
                metadata_=None,
                created_at=now,
            )
        )
    monkeypatch.setattr(operations, "generate_id", lambda: "duplicate-event")

    with pytest.raises(IntegrityError):
        operations.start_ticket_work("ticket", "agent-a")

    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        event_count = session.scalar(
            select(func.count()).select_from(db_models.Event)
        )
        assert ticket.status is constants.Status.OPEN
        assert event_count == 1


def test_competing_start_work_requests_change_ticket_only_once(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed(test_engine, _ticket("ticket", now), now)
    start_together = Barrier(2)

    def start_work():
        start_together.wait()
        return operations.start_ticket_work("ticket", "agent-a")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: start_work(), range(2)))

    assert sorted(result.outcome.value for result in results) == [
        constants.StartWorkOutcome.STARTED.value,
        constants.StartWorkOutcome.TICKET_ALREADY_STARTED.value,
    ]
    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        event_count = session.scalar(
            select(func.count()).select_from(db_models.Event)
        )
        assert ticket.status is constants.Status.IN_PROGRESS
        assert event_count == 1


def test_start_work_service_invalidates_cache_only_after_success(
    monkeypatch,
    make_user,
    make_ticket,
):
    requester = make_user(id="agent-a", role=constants.Role.AGENT)
    started_ticket = make_ticket(
        assigned_agent_id=requester.id,
        status=constants.Status.IN_PROGRESS,
    )
    invalidated = []
    monkeypatch.setattr(
        tickets_service.operations,
        "start_ticket_work",
        lambda *_: operations.StartWorkResult(
            constants.StartWorkOutcome.STARTED,
            started_ticket,
        ),
    )
    monkeypatch.setattr(
        tickets_service,
        "delete_cached_ticket",
        lambda ticket_id: invalidated.append(ticket_id) or True,
    )

    result = tickets_service.start_ticket_work(started_ticket.id, requester)

    assert result.status is constants.Status.IN_PROGRESS
    assert invalidated == [started_ticket.id]


@pytest.mark.parametrize(
    ("outcome", "expected_error", "expected_message"),
    [
        (
            constants.StartWorkOutcome.TICKET_UNASSIGNED,
            TicketStartWorkConflictError,
            "ticket_is_unassigned",
        ),
        (
            constants.StartWorkOutcome.TICKET_ALREADY_STARTED,
            TicketStartWorkConflictError,
            "ticket_is_already_started",
        ),
        (
            constants.StartWorkOutcome.TICKET_NOT_OPEN,
            TicketStartWorkConflictError,
            "ticket_is_not_open",
        ),
        (
            constants.StartWorkOutcome.ASSIGNED_TO_ANOTHER_AGENT,
            AuthorizationError,
            "ticket_assigned_to_another_agent",
        ),
    ],
)
def test_start_work_service_maps_state_to_clear_domain_error(
    monkeypatch,
    make_user,
    outcome,
    expected_error,
    expected_message,
):
    requester = make_user(id="agent-a", role=constants.Role.AGENT)
    monkeypatch.setattr(
        tickets_service.operations,
        "start_ticket_work",
        lambda *_: operations.StartWorkResult(outcome),
    )

    with pytest.raises(expected_error) as exc_info:
        tickets_service.start_ticket_work("ticket", requester)

    assert exc_info.value.message == expected_message


def test_non_agent_cannot_call_start_work_service(
    monkeypatch,
    make_user,
):
    requester = make_user(id="manager", role=constants.Role.MANAGER)
    monkeypatch.setattr(
        tickets_service.operations,
        "start_ticket_work",
        lambda *_: pytest.fail("unauthorized role must not reach the database"),
    )

    with pytest.raises(AuthorizationError) as exc_info:
        tickets_service.start_ticket_work("ticket", requester)

    assert exc_info.value.message == "only_assigned_agent_can_start_work"


def test_start_work_endpoint_uses_authenticated_requester(
    monkeypatch,
    make_user,
    make_ticket,
):
    requester = make_user(id="agent-a", role=constants.Role.AGENT)
    started_ticket = make_ticket(
        assigned_agent_id=requester.id,
        status=constants.Status.IN_PROGRESS,
    )
    captured = {}
    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_start_work(ticket_id, current_user):
        captured["ticket_id"] = ticket_id
        captured["requester"] = current_user
        return started_ticket

    monkeypatch.setattr(
        tickets_router.s_tickets,
        "start_ticket_work",
        fake_start_work,
    )

    response = client.post("/tickets/ticket/start-work")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == (
        constants.Status.IN_PROGRESS.value
    )
    assert captured == {
        "ticket_id": "ticket",
        "requester": requester,
    }


@pytest.mark.parametrize(
    ("domain_error", "expected_status", "expected_code"),
    [
        (
            TicketStartWorkConflictError("ticket_is_already_started"),
            409,
            "ticket_start_work_conflict",
        ),
        (
            AuthorizationError("ticket_assigned_to_another_agent"),
            403,
            "authorization_error",
        ),
    ],
)
def test_start_work_endpoint_preserves_clear_domain_error_shape(
    monkeypatch,
    make_user,
    domain_error,
    expected_status,
    expected_code,
):
    requester = make_user(id="agent-a", role=constants.Role.AGENT)
    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_start_work(*_):
        raise domain_error

    monkeypatch.setattr(
        tickets_router.s_tickets,
        "start_ticket_work",
        fake_start_work,
    )

    response = client.post("/tickets/ticket/start-work")

    assert response.status_code == expected_status
    assert response.json()["error"] == {
        "code": expected_code,
        "message": domain_error.message,
    }


def test_start_work_endpoint_requires_authentication():
    response = client.post("/tickets/ticket/start-work")

    assert response.status_code == 401


def test_get_ticket_leaves_open_ticket_unchanged(
    monkeypatch,
    tmp_path,
    make_user,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed(test_engine, _ticket("ticket", now), now)
    requester = make_user(id="agent-a", role=constants.Role.AGENT)
    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester
    monkeypatch.setattr(tickets_service, "check_cached_ticket", lambda _: None)
    monkeypatch.setattr(tickets_service, "cache_ticket", lambda _: True)
    monkeypatch.setattr(
        tickets_service.operations,
        "start_ticket_work",
        lambda *_: pytest.fail("GET must never start ticket work"),
    )

    response = client.get("/tickets/ticket")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == constants.Status.OPEN.value
    with Session(test_engine) as session:
        ticket = session.get(db_models.Ticket, "ticket")
        event_count = session.scalar(
            select(func.count()).select_from(db_models.Event)
        )
        assert ticket.status is constants.Status.OPEN
        assert event_count == 0


def test_claim_and_manual_assignment_leave_ticket_open(
    monkeypatch,
    tmp_path,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    with Session(test_engine) as session, session.begin():
        session.add_all(
            [
                _user("customer", constants.Role.USER, now),
                _user("agent-a", constants.Role.AGENT, now),
                _user("agent-b", constants.Role.AGENT, now),
                db_models.AgentProfile(
                    user_id="agent-a",
                    availability_status=constants.AvailabilityStatus.AVAILABLE,
                    availability_reason=None,
                    availability_note=None,
                    unavailable_until=None,
                    max_active_tickets=3,
                    last_assigned_at=None,
                    department_id="support",
                    created_at=now,
                    updated_at=now,
                ),
                db_models.AgentProfile(
                    user_id="agent-b",
                    availability_status=constants.AvailabilityStatus.AVAILABLE,
                    availability_reason=None,
                    availability_note=None,
                    unavailable_until=None,
                    max_active_tickets=3,
                    last_assigned_at=None,
                    department_id="support",
                    created_at=now,
                    updated_at=now,
                ),
                _ticket(
                    "claimed",
                    now,
                    assigned_agent_id=None,
                    status=constants.Status.NEW,
                ),
                _ticket(
                    "assigned",
                    now,
                    assigned_agent_id=None,
                    status=constants.Status.NEW,
                ),
            ]
        )

    claimed = operations.claim_ticket("claimed", "agent-a")
    assigned = operations.assign_ticket("assigned", "agent-a")
    reassigned = operations.assign_ticket("assigned", "agent-b")

    assert claimed.status is constants.Status.OPEN
    assert assigned.status is constants.Status.OPEN
    assert reassigned.status is constants.Status.OPEN


def test_manager_patch_assignment_forces_open_and_rejects_implicit_start(
    monkeypatch,
    make_user,
    make_ticket,
):
    requester = make_user(id="manager", role=constants.Role.MANAGER)
    agent = make_user(id="agent-b", role=constants.Role.AGENT)
    ticket = make_ticket(
        assigned_agent_id="agent-a",
        status=constants.Status.IN_PROGRESS,
        tags=constants.serialize_tags([]),
    )
    captured = {}
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda _: ticket)
    monkeypatch.setattr(tickets_service.operations, "get_user", lambda _: agent)

    def fake_update(_ticket_id, info, _event):
        captured.update(info)
        ticket.assigned_agent_id = info["assigned_agent_id"]
        ticket.status = info["status"]
        return ticket

    monkeypatch.setattr(
        tickets_service.operations,
        "update_ticket",
        fake_update,
    )
    monkeypatch.setattr(tickets_service, "delete_cached_ticket", lambda _: True)

    result = tickets_service.update_ticket(
        ticket.id,
        tickets_service.api_models.TicketUpdate(
            assigned_agent_id=agent.id,
        ),
        requester,
    )

    assert captured["status"] is constants.Status.OPEN
    assert result.status is constants.Status.OPEN


def test_generic_patch_cannot_replace_start_work_endpoint(
    monkeypatch,
    make_user,
    make_ticket,
):
    requester = make_user(id="agent-a", role=constants.Role.AGENT)
    ticket = make_ticket(
        assigned_agent_id=requester.id,
        status=constants.Status.OPEN,
        tags=constants.serialize_tags([]),
    )
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda _: ticket)
    monkeypatch.setattr(
        tickets_service.operations,
        "update_ticket",
        lambda *_: pytest.fail("OPEN -> IN_PROGRESS must use start-work"),
    )

    with pytest.raises(TicketStartWorkConflictError) as exc_info:
        tickets_service.update_ticket(
            ticket.id,
            tickets_service.api_models.TicketUpdate(
                status=constants.Status.IN_PROGRESS,
            ),
            requester,
        )

    assert exc_info.value.message == "use_start_work_endpoint"
