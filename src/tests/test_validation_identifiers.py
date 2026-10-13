"""Regression tests for non-string shared identifiers (repair plan A, finding 12).

The shared ``BeforeValidator`` helpers run before Pydantic type coercion. A raw
non-string (int, float, list, dict, bool) used to reach ``.strip()`` and raise
``AttributeError``, which Pydantic does not turn into a validation error, so the
routes returned 500. These tests pin the intended contract: a clean 422 in the
shared error envelope, with no raw input or password echoed back.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from main import app
from src import models
from src.routers import auth as auth_router
from src.routers import users as users_router

client = TestClient(app, raise_server_exceptions=False)

RAW_INPUT_SENTINEL = "raw-input-must-not-be-echoed"
PASSWORD_SENTINEL = "sensitive-password-must-not-be-echoed"

NON_STRING_IDENTIFIERS = [
    pytest.param(123, id="int"),
    pytest.param(1.5, id="float"),
    pytest.param([RAW_INPUT_SENTINEL], id="list"),
    pytest.param({RAW_INPUT_SENTINEL: True}, id="dict"),
    pytest.param(True, id="bool"),
    pytest.param("", id="empty-string"),
    pytest.param(None, id="null"),
]

IDENTIFIER_FIELDS = ["nickname", "email"]


def _assert_validation_error(response):
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert RAW_INPUT_SENTINEL not in response.text
    assert PASSWORD_SENTINEL not in response.text


@pytest.mark.parametrize("field", IDENTIFIER_FIELDS)
@pytest.mark.parametrize("identifier", NON_STRING_IDENTIFIERS)
def test_login_rejects_non_string_identifier(field, identifier):
    response = client.post(
        "/auth/login",
        json={field: identifier, "password": PASSWORD_SENTINEL},
    )

    _assert_validation_error(response)


def _registration_payload():
    return {
        "nickname": "new-user",
        "first_name": "New",
        "last_name": "User",
        "password": PASSWORD_SENTINEL,
        "phone": "+15550100",
        "email": "new-user@example.com",
    }


@pytest.mark.parametrize("field", IDENTIFIER_FIELDS)
@pytest.mark.parametrize("identifier", NON_STRING_IDENTIFIERS)
def test_registration_rejects_non_string_identifier(field, identifier):
    payload = _registration_payload()
    payload[field] = identifier

    response = client.post("/users/", json=payload)

    _assert_validation_error(response)


@pytest.mark.parametrize("field", IDENTIFIER_FIELDS)
@pytest.mark.parametrize("identifier", NON_STRING_IDENTIFIERS)
def test_profile_update_rejects_non_string_identifier(field, identifier, make_user):
    app.dependency_overrides[users_router.get_current_user] = lambda: make_user()

    response = client.patch("/users/user-1", json={field: identifier})

    _assert_validation_error(response)


def test_nickname_normalizes_whitespace_and_case():
    request = models.LoginRequest.model_validate(
        {"nickname": "  Mary-Jane  ", "password": PASSWORD_SENTINEL}
    )

    assert request.nickname == "mary-jane"


def test_email_normalizes_whitespace_and_domain_case():
    request = models.LoginRequest.model_validate(
        {"email": "  Mary@Example.COM  ", "password": PASSWORD_SENTINEL}
    )

    assert request.email == "Mary@example.com"


def test_valid_nickname_login_uses_normalized_identifier(monkeypatch, make_user):
    captured = {}
    user = make_user(id="login-user")

    def fake_login(identifier, password):
        captured["identifier"] = identifier
        captured["password"] = password
        return user

    monkeypatch.setattr(auth_router, "login_user", fake_login)
    monkeypatch.setattr(auth_router.security, "create_access_token", lambda _user: "access-token")
    monkeypatch.setattr(
        auth_router,
        "create_refresh_session_for_user",
        lambda _user_id: SimpleNamespace(refresh_token="refresh-token"),
    )

    response = client.post(
        "/auth/login",
        json={"nickname": "  Mary-Jane  ", "password": PASSWORD_SENTINEL},
    )

    assert response.status_code == 200, response.text
    assert captured["identifier"] == "mary-jane"
    assert captured["password"] == PASSWORD_SENTINEL
    assert PASSWORD_SENTINEL not in response.text
    body = response.json()
    assert body["access_token"] == "access-token"
    assert body["refresh_token"] == "refresh-token"


def test_registration_identifier_annotations_accept_valid_strings():
    user_create = models.UserCreate(
        nickname="  Mixed-Case  ",
        first_name="New",
        last_name="User",
        password=PASSWORD_SENTINEL,
        phone="+15550100",
        email="  Mixed@Example.COM  ",
    )

    assert user_create.nickname == "mixed-case"
    assert user_create.email == "Mixed@example.com"
