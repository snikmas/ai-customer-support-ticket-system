import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from main import app
from src import constants
from src import models as api_models
from src.db import models as db_models
from src.db import operations
from src.routers import tickets as tickets_router
from src.services import tickets as tickets_service
from src.exceptions.domain import AuthorizationError, TicketStatusConflictError


client = TestClient(app)


def _user(user_id: str, role: constants.Role, now: datetime) -> db_models.User:
    return db_models.User(
        id=user_id,
        nickname=user_id,
        avatar_url=None,
        first_name="History",
        last_name="Tester",
        phone=f"phone-{user_id}",
        email=f"{user_id}@example.com",
        role=role,
        password="hashed-password",
        updated_at=now,
        created_at=now,
        deleted_at=None,
        user_status=constants.UserStatus.ACTIVE,
    )


def _ticket(now: datetime) -> db_models.Ticket:
    return db_models.Ticket(
        id="ticket",
        title="History ticket",
        description="History description",
        category=constants.Category.ACCOUNT_ACCESS,
        tags=constants.serialize_tags([constants.Tag.API_KEY]),
        assigned_agent_id="agent",
        creator_user_id="customer",
        status=constants.Status.IN_PROGRESS,
        priority=constants.Priority.NORMAL,
        updated_at=now,
        created_at=now,
        deleted_at=None,
    )


def _event(
    event_id: str,
    event_type: constants.EventType,
    created_at: datetime,
    *,
    entity_type: constants.EntityType = constants.EntityType.TICKET,
    entity_id: str = "ticket",
    actor_user_id: str = "agent",
    old_value: dict | None = None,
    new_value: dict | None = None,
    metadata: str | None = None,
) -> db_models.Event:
    return db_models.Event(
        id=event_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        old_value=None if old_value is None else constants._audit_json(old_value),
        new_value=constants._audit_json(new_value or {}),
        metadata_=metadata,
        created_at=created_at,
    )


def _prepare_database(monkeypatch, tmp_path):
    from sqlalchemy import create_engine

    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'history.db'}")
    db_models.Base.metadata.create_all(test_engine)
    monkeypatch.setattr(operations, "engine", test_engine)
    return test_engine


def _seed_history(test_engine, now: datetime) -> None:
    public_comment = db_models.Comment(
        id="public-comment",
        ticket_id="ticket",
        author_user_id="customer",
        body="Public reply",
        visibility=constants.Visibility.PUBLIC,
        edited_at=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
        deleted_by_user_id=None,
        parent_comment_id=None,
        attachments_count=0,
        source=constants.Source.API,
    )
    internal_comment = db_models.Comment(
        id="internal-comment",
        ticket_id="ticket",
        author_user_id="agent",
        body="Internal note",
        visibility=constants.Visibility.INTERNAL,
        edited_at=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
        deleted_by_user_id=None,
        parent_comment_id=None,
        attachments_count=0,
        source=constants.Source.API,
    )
    event_specs = [
        ("01", 0, constants.EventType.TICKET_CREATED, {"status": constants.Status.NEW}),
        ("02", 1, constants.EventType.TICKET_UPDATED, {"tags": [constants.Tag.REDIS.value]}),
        ("03", 2, constants.EventType.TICKET_ASSIGNED, {
            "status": constants.Status.OPEN,
            "assigned_agent_id": "agent",
            "due_at": now + timedelta(hours=6),
        }),
        ("04", 3, constants.EventType.TICKET_CLAIMED, {"status": constants.Status.OPEN}),
        ("05", 4, constants.EventType.TICKET_STATUS_CHANGED, {"status": constants.Status.IN_PROGRESS}),
        ("08", 7, constants.EventType.TICKET_DELETED, {"deleted_at": now + timedelta(minutes=7)}),
    ]
    events = [
        _event(
            event_id,
            event_type,
            now + timedelta(minutes=minute),
            new_value=new_value,
            metadata="source=automatic_router" if event_id == "03" else None,
        )
        for event_id, minute, event_type, new_value in event_specs
    ]
    events.extend([
        _event(
            "06",
            constants.EventType.COMMENT_CREATED,
            now + timedelta(minutes=5),
            entity_type=constants.EntityType.COMMENT,
            entity_id=public_comment.id,
            actor_user_id="customer",
            new_value={"body": public_comment.body, "visibility": public_comment.visibility},
        ),
        _event(
            "07",
            constants.EventType.COMMENT_CREATED,
            now + timedelta(minutes=6),
            entity_type=constants.EntityType.COMMENT,
            entity_id=internal_comment.id,
            new_value={"body": internal_comment.body, "visibility": internal_comment.visibility},
        ),
    ])
    with Session(test_engine) as session, session.begin():
        session.add_all([
            _user("customer", constants.Role.USER, now),
            _user("agent", constants.Role.AGENT, now),
            _user("manager", constants.Role.MANAGER, now),
            _ticket(now),
            public_comment,
            internal_comment,
            *events,
        ])


def test_ticket_history_is_chronological_paginated_and_includes_mutation_types(
    monkeypatch,
    tmp_path,
    make_user,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed_history(test_engine, now)
    manager = make_user(id="manager", role=constants.Role.MANAGER)

    first_page = tickets_service.get_ticket_history("ticket", manager, 3, 0)
    second_page = tickets_service.get_ticket_history("ticket", manager, 5, 3)
    history = first_page + second_page

    assert [event.id for event in history] == [f"0{index}" for index in range(1, 9)]
    assert {event.event_type for event in history} >= {
        constants.EventType.TICKET_CREATED,
        constants.EventType.TICKET_UPDATED,
        constants.EventType.TICKET_ASSIGNED,
        constants.EventType.TICKET_CLAIMED,
        constants.EventType.TICKET_STATUS_CHANGED,
        constants.EventType.TICKET_DELETED,
        constants.EventType.COMMENT_CREATED,
    }


def test_customer_history_hides_internal_comments_and_staff_only_details(
    monkeypatch,
    tmp_path,
    make_user,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    _seed_history(test_engine, now)
    customer = make_user(id="customer", role=constants.Role.USER)

    history = tickets_service.get_ticket_history("ticket", customer, 20, 0)

    assert "07" not in {event.id for event in history}
    assignment = next(event for event in history if event.id == "03")
    assert assignment.new_value == {"status": constants.Status.OPEN.value}
    assert assignment.actor_user_id is None
    assert assignment.metadata is None
    public_comment = next(event for event in history if event.id == "06")
    assert public_comment.new_value == {
        "body": "Public reply",
        "visibility": constants.Visibility.PUBLIC.value,
    }


def test_ticket_history_endpoint_passes_pagination(monkeypatch, make_user):
    requester = make_user(id="customer")
    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester
    captured = {}

    def fake_history(ticket_id, current_user, limit, offset):
        captured.update(
            ticket_id=ticket_id,
            requester=current_user,
            limit=limit,
            offset=offset,
        )
        return []

    monkeypatch.setattr(tickets_router.s_tickets, "get_ticket_history", fake_history)

    response = client.get("/tickets/ticket/history?limit=5&offset=10")

    assert response.status_code == 200
    assert response.json() == {"data": []}
    assert captured == {
        "ticket_id": "ticket",
        "requester": requester,
        "limit": 5,
        "offset": 10,
    }


@pytest.mark.parametrize("mutation", ["update", "delete", "comment"])
def test_mutation_rolls_back_when_its_audit_event_cannot_be_saved(
    monkeypatch,
    tmp_path,
    mutation,
):
    test_engine = _prepare_database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    ticket_id = "ticket"
    comment_id = "comment"
    duplicate_event_id = "duplicate-event"
    ticket = _ticket(now)
    comment = db_models.Comment(
        id=comment_id,
        ticket_id=ticket_id,
        author_user_id="customer",
        body="Original",
        visibility=constants.Visibility.PUBLIC,
        edited_at=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
        deleted_by_user_id=None,
        parent_comment_id=None,
        attachments_count=0,
        source=constants.Source.API,
    )
    existing_event = _event(
        duplicate_event_id,
        constants.EventType.TICKET_CREATED,
        now,
        actor_user_id="customer",
    )
    with Session(test_engine) as session, session.begin():
        session.add_all([
            _user("customer", constants.Role.USER, now),
            _user("agent", constants.Role.AGENT, now),
            ticket,
            comment,
            existing_event,
        ])

    event_data = api_models.Event(
        id=duplicate_event_id,
        entity_type=(
            constants.EntityType.COMMENT
            if mutation == "comment"
            else constants.EntityType.TICKET
        ),
        entity_id=comment_id if mutation == "comment" else ticket_id,
        actor_user_id="customer",
        event_type=constants.EventType.TICKET_UPDATED,
        old_value=constants._audit_json({}),
        new_value=constants._audit_json({}),
        created_at=now,
    )

    with pytest.raises(IntegrityError):
        if mutation == "update":
            operations.update_ticket(
                ticket_id,
                {"status": constants.Status.RESOLVED},
                event_data,
            )
        elif mutation == "delete":
            operations.delete_ticket(
                ticket_id,
                {"deleted_at": now, "updated_at": now},
                event_data,
            )
        else:
            operations.update_comment_with_event(
                comment_id,
                {"body": "Changed"},
                event_data,
            )

    with Session(test_engine) as session:
        saved_ticket = session.get(db_models.Ticket, ticket_id)
        saved_comment = session.get(db_models.Comment, comment_id)
        assert saved_ticket.status is constants.Status.IN_PROGRESS
        assert saved_ticket.deleted_at is None
        assert saved_comment.body == "Original"


def test_authoritative_transition_rules_include_customer_close_and_reopen():
    assert constants.can_role_transition_ticket(
        constants.Role.USER,
        constants.Status.RESOLVED,
        constants.Status.CLOSED,
    )
    assert constants.can_role_transition_ticket(
        constants.Role.USER,
        constants.Status.CLOSED,
        constants.Status.REOPENED,
    )
    assert not constants.can_role_transition_ticket(
        constants.Role.USER,
        constants.Status.NEW,
        constants.Status.OPEN,
    )


def test_new_ticket_cannot_be_opened_without_claim_or_assignment(
    monkeypatch,
    make_user,
    make_ticket,
):
    manager = make_user(id="manager", role=constants.Role.MANAGER)
    ticket = make_ticket(status=constants.Status.NEW)
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda *_: ticket)

    with pytest.raises(TicketStatusConflictError) as exc_info:
        tickets_service.update_ticket(
            ticket.id,
            api_models.TicketUpdate(status=constants.Status.OPEN),
            manager,
        )

    assert exc_info.value.code == "ticket_status_conflict"


def test_terminal_ticket_must_be_reopened_before_assignment(
    monkeypatch,
    make_user,
    make_ticket,
):
    manager = make_user(id="manager", role=constants.Role.MANAGER)
    ticket = make_ticket(status=constants.Status.CLOSED)
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda *_: ticket)

    with pytest.raises(TicketStatusConflictError) as exc_info:
        tickets_service.assign_ticket(ticket.id, "agent", manager)

    assert exc_info.value.code == "ticket_status_conflict"


def test_manager_must_assign_instead_of_claiming(
    monkeypatch,
    make_user,
    make_ticket,
):
    manager = make_user(id="manager", role=constants.Role.MANAGER)
    ticket = make_ticket(status=constants.Status.NEW)
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda *_: ticket)

    with pytest.raises(AuthorizationError) as exc_info:
        tickets_service.claim_ticket(ticket.id, manager)

    assert exc_info.value.code == "only_agents_can_claim"
