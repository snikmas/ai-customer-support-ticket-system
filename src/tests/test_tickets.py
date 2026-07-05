from fastapi.testclient import TestClient

from main import app
from src import constants
from src.routers import tickets as tickets_router


client = TestClient(app)


def test_get_tickets_requires_authentication():
    response = client.get("/tickets/")

    assert response.status_code == 401


def test_get_tickets_returns_current_service_shape(monkeypatch, make_user, make_ticket):
    requester = make_user()
    ticket = make_ticket(id="ticket-visible", creator_user_id=requester.id)

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester
    monkeypatch.setattr(
        tickets_router.s_tickets,
        "get_all_tickets",
        lambda current_user: [ticket] if current_user is requester else [],
    )

    response = client.get("/tickets/")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "data" in body
    assert body["data"][0]["id"] == "ticket-visible"
    assert body["data"][0]["creator_user_id"] == requester.id


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


def test_claim_ticket_converts_permission_error_to_403(monkeypatch, make_user):
    requester = make_user(role=constants.Role.USER)

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_claim_ticket(ticket_id, current_user):
        raise PermissionError("only_agents_can_claim")

    monkeypatch.setattr(tickets_router.s_tickets, "claim_ticket", fake_claim_ticket)

    response = client.post("/tickets/ticket-1/claim")

    assert response.status_code == 403


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
