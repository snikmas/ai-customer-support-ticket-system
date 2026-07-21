from fastapi.testclient import TestClient
from datetime import datetime, timezone
import pytest

from main import app
from src import constants
from src.exceptions.domain import AlreadyDeletedError, AuthorizationError, InvalidAssigneeError
from src.db.models import Comment, Event, Ticket
from src.routers import tickets as tickets_router
from src.services import tickets as tickets_service


client = TestClient(app)


def test_ticket_create_rejects_client_status(make_user):
    app.dependency_overrides[tickets_router.get_current_user] = lambda: make_user()
    response = client.post(
        "/tickets/",
        json={
            "title": "Need help",
            "description": "Cannot use the API key",
            "category": constants.Category.ACCOUNT_ACCESS.value,
            "status": constants.Status.CLOSED.value,
        },
    )

    assert response.status_code == 422


def test_ticket_owner_can_update_tags(monkeypatch, make_user, make_ticket):
    requester = make_user(id="customer")
    ticket = make_ticket(creator_user_id=requester.id, tags=constants.serialize_tags([constants.Tag.API_KEY]))
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda ticket_id: ticket)
    monkeypatch.setattr(tickets_service.operations, "update_ticket", lambda ticket_id, info, event: ticket)

    result = tickets_service.update_ticket(
        ticket.id,
        tickets_service.api_models.TicketUpdate(tags=[constants.Tag.REDIS]),
        requester,
    )

    assert result.id == ticket.id


def test_ticket_owner_cannot_update_tags_after_new(monkeypatch, make_user, make_ticket):
    requester = make_user(id="customer")
    ticket = make_ticket(
        creator_user_id=requester.id,
        status=constants.Status.IN_PROGRESS,
        tags=constants.serialize_tags([constants.Tag.API_KEY]),
    )
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda ticket_id: ticket)

    try:
        tickets_service.update_ticket(
            ticket.id,
            tickets_service.api_models.TicketUpdate(tags=[constants.Tag.REDIS]),
            requester,
        )
    except AuthorizationError as error:
        assert error.code == "ticket_tags_locked_after_triage"
    else:
        raise AssertionError("customers must not change tags after triage starts")


def test_assigned_agent_can_update_tags_after_triage(monkeypatch, make_user, make_ticket):
    requester = make_user(id="agent-a", role=constants.Role.AGENT)
    ticket = make_ticket(
        assigned_agent_id=requester.id,
        status=constants.Status.IN_PROGRESS,
        tags=constants.serialize_tags([constants.Tag.API_KEY]),
    )
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda ticket_id: ticket)
    monkeypatch.setattr(tickets_service.operations, "update_ticket", lambda ticket_id, info, event: ticket)

    result = tickets_service.update_ticket(
        ticket.id,
        tickets_service.api_models.TicketUpdate(tags=[constants.Tag.REDIS]),
        requester,
    )

    assert result.id == ticket.id


def test_unassigned_agent_cannot_update_tags(monkeypatch, make_user, make_ticket):
    requester = make_user(id="agent-a", role=constants.Role.AGENT)
    ticket = make_ticket(
        assigned_agent_id=None,
        status=constants.Status.NEW,
        tags=constants.serialize_tags([constants.Tag.API_KEY]),
    )
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda ticket_id: ticket)

    try:
        tickets_service.update_ticket(
            ticket.id,
            tickets_service.api_models.TicketUpdate(tags=[constants.Tag.REDIS]),
            requester,
        )
    except AuthorizationError as error:
        assert error.code == "ticket_not_assigned_to_requester"
    else:
        raise AssertionError("an agent must claim or receive the ticket before changing tags")


def test_ticket_detail_rejects_another_customer(monkeypatch, make_user, make_ticket):
    requester = make_user(id="customer-a", role=constants.Role.USER)
    ticket = make_ticket(id="ticket-b", creator_user_id="customer-b")

    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda ticket_id: ticket)

    try:
        tickets_service.get_ticket(ticket.id, requester)
    except AuthorizationError:
        pass
    else:
        raise AssertionError("another customer's ticket must not be readable")


def test_agent_list_and_detail_share_support_queue_policy(monkeypatch, make_user, make_ticket):
    requester = make_user(id="agent-a", role=constants.Role.AGENT)
    assigned = make_ticket(id="assigned", assigned_agent_id=requester.id, status=constants.Status.IN_PROGRESS)
    claimable = make_ticket(id="claimable", assigned_agent_id=None, status=constants.Status.NEW)
    another_agents = make_ticket(id="someone-elses", assigned_agent_id="agent-b", status=constants.Status.IN_PROGRESS)
    tickets = [assigned, claimable, another_agents]

    monkeypatch.setattr(tickets_service.operations, "get_tickets", lambda *args: tickets)
    visible = tickets_service.get_all_tickets(requester, 20, 0, "created_at", "desc", None, None)
    assert {ticket.id for ticket in visible} == {"assigned", "claimable"}

    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda ticket_id: claimable)
    assert tickets_service.get_ticket(claimable.id, requester).id == claimable.id

    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda ticket_id: another_agents)
    try:
        tickets_service.get_ticket(another_agents.id, requester)
    except AuthorizationError:
        pass
    else:
        raise AssertionError("an agent must not read another agent's assigned ticket")


def test_manager_and_readonly_agent_list_all_non_deleted_tickets(monkeypatch, make_user, make_ticket):
    first = make_ticket(id="first")
    second = make_ticket(id="second", assigned_agent_id="agent-b", status=constants.Status.IN_PROGRESS)
    monkeypatch.setattr(tickets_service.operations, "get_tickets", lambda *args: [first, second])

    for role in [constants.Role.MANAGER, constants.Role.AGENT_READONLY]:
        requester = make_user(role=role)
        visible = tickets_service.get_all_tickets(requester, 20, 0, "created_at", "desc", None, None)
        assert {ticket.id for ticket in visible} == {"first", "second"}


def test_ticket_domain_error_has_consistent_http_shape(monkeypatch, make_user):
    requester = make_user(id="customer-a", role=constants.Role.USER)
    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_get_ticket(ticket_id, current_user):
        raise AuthorizationError()

    monkeypatch.setattr(tickets_router.s_tickets, "get_ticket", fake_get_ticket)

    response = client.get("/tickets/ticket-b")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "authorization_error",
            "message": "Permission denied",
        }
    }


def _ondelete(model, column_name: str) -> str | None:
    column = model.__table__.columns[column_name]
    foreign_key = next(iter(column.foreign_keys))
    return foreign_key.ondelete


def test_required_history_references_do_not_use_set_null():
    assert Ticket.__table__.columns.creator_user_id.nullable is False
    assert _ondelete(Ticket, "creator_user_id") == "RESTRICT"

    assert Event.__table__.columns.actor_user_id.nullable is True
    assert _ondelete(Event, "actor_user_id") == "RESTRICT"

    assert Comment.__table__.columns.author_user_id.nullable is False
    assert _ondelete(Comment, "author_user_id") == "RESTRICT"


def test_get_tickets_requires_authentication():
    response = client.get("/tickets/")

    assert response.status_code == 401


def test_get_tickets_returns_current_service_shape(monkeypatch, make_user, make_ticket):
    requester = make_user()
    ticket = make_ticket(id="ticket-visible", creator_user_id=requester.id)

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester
    captured = {}

    def fake_get_all_tickets(
        current_user,
        limit,
        offset,
        sort_by,
        sort_order,
        priority,
        status,
        overdue,
    ):
        captured.update(
            {
                "current_user": current_user,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "priority": priority,
                "status": status,
                "overdue": overdue,
            }
        )
        return [ticket] if current_user is requester else []

    monkeypatch.setattr(tickets_router.s_tickets, "get_all_tickets", fake_get_all_tickets)

    response = client.get("/tickets/")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "data" in body
    assert body["data"][0]["id"] == "ticket-visible"
    assert body["data"][0]["creator_user_id"] == requester.id
    assert captured == {
        "current_user": requester,
        "limit": constants.DEFAULT_PAGE_LIMIT,
        "offset": 0,
        "sort_by": constants.DEFAULT_SORT_BY,
        "sort_order": constants.DEFAULT_SORT_ORDER,
        "priority": None,
        "status": None,
        "overdue": None,
    }


def test_create_ticket_uses_authenticated_requester(monkeypatch, make_user, make_ticket):
    requester = make_user(id="creator-user")
    created_ticket = make_ticket(id="created-ticket", creator_user_id=requester.id)
    captured = {}

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_create_ticket(ticket_create, current_user):
        captured["ticket_create"] = ticket_create
        captured["requester"] = current_user
        return created_ticket

    monkeypatch.setattr(tickets_router.s_tickets, "create_ticket", fake_create_ticket)

    response = client.post(
        "/tickets/",
        json={
            "title": "Need help",
            "description": "Cannot use the API key",
            "category": constants.Category.ACCOUNT_ACCESS.value,
            "tags": [constants.Tag.API_KEY.value],
            "department_id": "support",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["id"] == "created-ticket"
    assert captured["requester"] is requester
    assert captured["ticket_create"].category == constants.Category.ACCOUNT_ACCESS


def test_update_ticket_uses_body_and_authenticated_requester(
    monkeypatch,
    make_user,
    make_ticket,
):
    requester = make_user(id="manager-user", role=constants.Role.MANAGER)
    updated_ticket = make_ticket(
        id="ticket-1",
        priority=constants.Priority.HIGH,
        status=constants.Status.OPEN,
    )
    captured = {}

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_update_ticket(ticket_id, new_info, current_user):
        captured["ticket_id"] = ticket_id
        captured["new_info"] = new_info
        captured["requester"] = current_user
        return updated_ticket

    monkeypatch.setattr(tickets_router.s_tickets, "update_ticket", fake_update_ticket)

    response = client.patch(
        "/tickets/ticket-1",
        json={"status": constants.Status.OPEN.value, "priority": constants.Priority.HIGH.value},
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["priority"] == constants.Priority.HIGH.value
    assert captured["ticket_id"] == "ticket-1"
    assert captured["new_info"].status == constants.Status.OPEN
    assert captured["requester"] is requester


def test_claim_ticket_returns_domain_authorization_error(monkeypatch, make_user):
    requester = make_user(role=constants.Role.USER)

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_claim_ticket(ticket_id, current_user):
        raise AuthorizationError("Only agents can claim tickets", code="only_agents_can_claim")

    monkeypatch.setattr(tickets_router.s_tickets, "claim_ticket", fake_claim_ticket)

    response = client.post("/tickets/ticket-1/claim")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "only_agents_can_claim"


def test_assign_ticket_uses_agent_id_body(monkeypatch, make_user, make_ticket):
    requester = make_user(id="manager-user", role=constants.Role.MANAGER)
    assigned_ticket = make_ticket(
        id="ticket-1",
        assigned_agent_id="agent-user",
        status=constants.Status.IN_PROGRESS,
    )
    captured = {}

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_assign_ticket(ticket_id, agent_id, current_user):
        captured["ticket_id"] = ticket_id
        captured["agent_id"] = agent_id
        captured["requester"] = current_user
        return assigned_ticket

    monkeypatch.setattr(tickets_router.s_tickets, "assign_ticket", fake_assign_ticket)

    response = client.post("/tickets/ticket-1/assign", json={"agent_id": "agent-user"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["assigned_agent_id"] == "agent-user"
    assert captured == {
        "ticket_id": "ticket-1",
        "agent_id": "agent-user",
        "requester": requester,
    }


def test_manager_can_assign_ticket_to_agent(monkeypatch, make_user, make_ticket):
    requester = make_user(id="manager-1", role=constants.Role.MANAGER)
    agent = make_user(id="agent-1", role=constants.Role.AGENT)
    ticket = make_ticket(id="ticket-1", assigned_agent_id=None)

    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda _: ticket)
    monkeypatch.setattr(tickets_service.operations, "get_user", lambda _: agent)
    monkeypatch.setattr(tickets_service.operations, "assign_ticket", lambda *_: ticket)
    monkeypatch.setattr(tickets_service, "_require_same_active_department", lambda *_: None)

    tickets_service.assign_ticket(ticket.id, agent.id, requester)


def test_manager_cannot_be_ticket_assignee(monkeypatch, make_user, make_ticket):
    requester = make_user(id="admin-1", role=constants.Role.ADMIN)
    manager = make_user(id="manager-1", role=constants.Role.MANAGER)
    ticket = make_ticket(id="ticket-1", assigned_agent_id=None)

    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda _: ticket)
    monkeypatch.setattr(tickets_service.operations, "get_user", lambda _: manager)

    with pytest.raises(InvalidAssigneeError) as exc_info:
        tickets_service.assign_ticket(ticket.id, manager.id, requester)

    assert exc_info.value.code == "assignee_must_be_agent"


def test_repeated_ticket_delete_is_rejected_before_new_event(monkeypatch, make_user, make_ticket):
    requester = make_user(id="owner-1")
    ticket = make_ticket(id="ticket-1", creator_user_id=requester.id)
    ticket.deleted_at = datetime.now(timezone.utc)
    monkeypatch.setattr(tickets_service.operations, "get_ticket", lambda _: ticket)
    monkeypatch.setattr(
        tickets_service.operations,
        "delete_ticket",
        lambda *_: pytest.fail("a repeated delete must not reach persistence"),
    )

    with pytest.raises(AlreadyDeletedError):
        tickets_service.delete_ticket(ticket.id, requester)
