"""Guard the shared error contract in notes/stage-1-error-contract.md.

Routers and dependencies must surface only domain exceptions, so every client
error uses the shared envelope with a stable machine code. The generic
`http_<status>` codes exist only as a fallback in the HTTPException handler and
must not appear for expected business failures.
"""

from fastapi.testclient import TestClient

from main import app
from src.exceptions.domain import TicketNotFoundError
from src.routers import tickets as tickets_router
from src.services import tickets as tickets_service

# raise_server_exceptions=False lets the catch-all Exception handler produce
# its real 500 response instead of re-raising inside the test.
client = TestClient(app, raise_server_exceptions=False)


def test_missing_credentials_returns_domain_401_envelope():
    response = client.get("/tickets/")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "authentication_error"
    assert body["error"]["message"]


def test_domain_not_found_uses_stable_code(monkeypatch, make_user):
    app.dependency_overrides[tickets_router.get_current_user] = lambda: make_user()

    def missing(ticket_id, requester):
        raise TicketNotFoundError()

    monkeypatch.setattr(tickets_service, "get_ticket", missing)

    response = client.get("/tickets/missing-ticket")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "ticket_not_found"
    assert not body["error"]["code"].startswith("http_")


def test_request_validation_uses_shared_envelope(make_user):
    app.dependency_overrides[tickets_router.get_current_user] = lambda: make_user()

    response = client.post("/tickets/", json={"title": "missing fields"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]


def test_unexpected_exception_returns_safe_500(monkeypatch, make_user):
    app.dependency_overrides[tickets_router.get_current_user] = lambda: make_user()

    def explode(ticket_id, requester):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(tickets_service, "get_ticket", explode)

    response = client.get("/tickets/any-ticket")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_server_error"
    # Low-level details are logged, never returned to clients.
    assert "sensitive internal detail" not in response.text
