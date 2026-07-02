from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.core import security
from src.dependencies import auth as auth_dependency
from src.services import auth as auth_service


def test_hash_password_returns_verifiable_text_hash():
    plain_password = "correct-password"

    hashed_password = security.hash_password(plain_password)

    assert isinstance(hashed_password, str)
    assert hashed_password.startswith("$2")
    assert not hashed_password.startswith("b'")
    assert hashed_password != plain_password
    assert security.verify_password(plain_password, hashed_password) is True
    assert security.verify_password("wrong-password", hashed_password) is False


def test_login_user_returns_user_for_valid_nickname_password(monkeypatch):
    user = SimpleNamespace(
        nickname="mary",
        email="mary@example.com",
        password=security.hash_password("correct-password"),
    )

    monkeypatch.setattr(
        auth_service.operations,
        "get_user_by_nickname",
        lambda nickname: user if nickname == "mary" else None,
    )

    result = auth_service.login_user("mary", "correct-password")

    assert result is user


def test_login_user_returns_none_for_unknown_user(monkeypatch):
    monkeypatch.setattr(
        auth_service.operations,
        "get_user_by_nickname",
        lambda nickname: None,
    )

    result = auth_service.login_user("missing-user", "any-password")

    assert result is None


def test_login_user_returns_none_for_wrong_password(monkeypatch):
    user = SimpleNamespace(password=security.hash_password("correct-password"))

    monkeypatch.setattr(
        auth_service.operations,
        "get_user_by_nickname",
        lambda nickname: user,
    )

    result = auth_service.login_user("mary", "wrong-password")

    assert result is None


def test_get_current_user_decodes_bearer_token_and_loads_user(monkeypatch):
    user = SimpleNamespace(id="user-1")
    captured = {}

    def fake_decode_access_token(token):
        captured["token"] = token
        return {"sub": "user-1"}

    monkeypatch.setattr(
        auth_dependency.security,
        "decode_access_token",
        fake_decode_access_token,
    )
    monkeypatch.setattr(
        auth_dependency.operations,
        "get_user",
        lambda user_id: user if user_id == "user-1" else None,
    )

    result = auth_dependency.get_current_user("Bearer abc.def.ghi")

    assert result is user
    assert captured["token"] == "abc.def.ghi"


def test_get_current_user_rejects_missing_authorization_header():
    with pytest.raises(HTTPException) as exc_info:
        auth_dependency.get_current_user(None)

    assert exc_info.value.status_code == 401
