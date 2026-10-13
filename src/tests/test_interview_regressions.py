"""Request-boundary and permission regressions found during interview rehearsal."""

import pytest
from fastapi.testclient import TestClient

from main import app
from src import constants, models
from src.exceptions import AuthorizationError, InvalidAssigneeError
from src.services import tickets, users


@pytest.mark.parametrize("model,field", [
    (models.TicketUpdate, "priority"),
    (models.TicketUpdate, "status"),
    (models.TicketUpdate, "assigned_agent_id"),
    (models.TicketUpdate, "tags"),
    (models.CommentUpdate, "body"),
    (models.CommentUpdate, "visibility"),
    (models.UserUpdate, "first_name"),
    (models.UserUpdate, "nickname"),
    (models.UserUpdate, "password"),
    (models.UserUpdate, "role"),
    (models.AgentProfileManagementUpdate, "max_active_tickets"),
])
def test_update_rejects_explicit_null_but_allows_omission(model, field):
    model.model_validate({})
    with pytest.raises(ValueError):
        model.model_validate({field: None})


def test_validation_errors_do_not_echo_passwords():
    response = TestClient(app).post("/auth/login", json={
        "nickname": "audit-user", "email": "audit@example.com",
        "password": "synthetic-sensitive-input",
    })
    assert response.status_code == 422
    assert "synthetic-sensitive-input" not in response.text


def test_patch_assignment_checks_department(monkeypatch, make_user, make_ticket):
    manager = make_user(role=constants.Role.MANAGER)
    agent = make_user(id="other-agent", role=constants.Role.AGENT)
    ticket = make_ticket()
    monkeypatch.setattr(tickets.operations, "get_ticket", lambda _: ticket)
    monkeypatch.setattr(tickets.operations, "get_user", lambda _: agent)

    def reject_department(*args, **kwargs):
        raise InvalidAssigneeError(code="assignee_department_mismatch")

    monkeypatch.setattr(tickets, "_require_same_active_department", reject_department)
    monkeypatch.setattr(tickets.operations, "update_ticket", lambda *args: pytest.fail("must reject before write"))
    with pytest.raises(InvalidAssigneeError):
        tickets.update_ticket(ticket.id, models.TicketUpdate(assigned_agent_id=agent.id), manager)


def test_admin_cannot_edit_superadmin_profile(monkeypatch, make_user):
    admin = make_user(id="admin", role=constants.Role.ADMIN)
    root = make_user(id="root", role=constants.Role.SUPER_ADMIN)
    monkeypatch.setattr(users.operations, "get_user", lambda uid: admin if uid == admin.id else root)
    monkeypatch.setattr(users.operations, "update_user", lambda *args: pytest.fail("must reject before write"))
    with pytest.raises(AuthorizationError):
        users.update_user(root.id, models.UserUpdate(first_name="Changed"), admin)


def test_admin_cannot_promote_self_to_superadmin(monkeypatch, make_user):
    admin = make_user(id="admin", role=constants.Role.ADMIN)
    monkeypatch.setattr(users.operations, "get_user", lambda _: admin)
    monkeypatch.setattr(users.operations, "get_agent_profile", lambda _: None)
    monkeypatch.setattr(users.operations, "update_user", lambda *args: pytest.fail("must reject before write"))
    with pytest.raises(AuthorizationError):
        users.update_user(admin.id, models.UserUpdate(role=constants.Role.SUPER_ADMIN), admin)


def test_update_uniqueness_conflict_has_domain_error(monkeypatch, make_user):
    from sqlalchemy.exc import IntegrityError
    from src.exceptions import UserAlreadyExistsError
    user = make_user()
    monkeypatch.setattr(users.operations, "get_user", lambda _: user)

    def duplicate(*args, **kwargs):
        raise IntegrityError("synthetic", {}, Exception("duplicate"))

    monkeypatch.setattr(users.operations, "update_user", duplicate)
    with pytest.raises(UserAlreadyExistsError):
        users.update_user(user.id, models.UserUpdate(nickname="duplicate-name"), user)
