from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi import HTTPException

from src import constants
from src.core import security
from src.dependencies import auth as auth_dependency
from src.services import auth as auth_service


def test_hash_password_returns_verifiable_text_hash():
    plain_password = "correct-password"

    hashed_password = security.hash_password(plain_password)

    assert isinstance(hashed_password, str)
    assert hashed_password.startswith("$argon2id$")
    assert not hashed_password.startswith("b'")
    assert hashed_password != plain_password
    assert security.verify_password(plain_password, hashed_password) is True
    assert security.verify_password("wrong-password", hashed_password) is False


def test_login_user_returns_user_for_valid_nickname_password(monkeypatch, make_user):
    user = make_user(
        id="auth-user",
        nickname="mary",
        user_status=constants.UserStatus.ACTIVE,
    )
    user.password = security.hash_password("correct-password")

    monkeypatch.setattr(
        auth_service.operations,
        "get_user_by_nickname",
        lambda nickname: user if nickname == "mary" else None,
    )

    result = auth_service.login_user("mary", "correct-password")

    assert result is user


def test_login_upgrades_legacy_bcrypt_hash_to_argon2(monkeypatch, make_user):
    password = "legacy-password"
    user = make_user(id="legacy-user", nickname="mary")
    user.password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    captured = {}

    monkeypatch.setattr(auth_service.operations, "get_user_by_nickname", lambda _: user)

    def fake_update_user(user_id, updated_info, event_data=None):
        captured["user_id"] = user_id
        captured["password"] = updated_info["password"]
        user.password = updated_info["password"]
        return user

    monkeypatch.setattr(auth_service.operations, "update_user", fake_update_user)

    result = auth_service.login_user("mary", password)

    assert result is user
    assert captured["user_id"] == "legacy-user"
    assert captured["password"].startswith("$argon2id$")


def test_login_user_returns_none_for_inactive_user(monkeypatch, make_user):
    user = make_user(user_status=constants.UserStatus.BANNED)
    user.password = security.hash_password("correct-password")

    monkeypatch.setattr(auth_service.operations, "get_user_by_nickname", lambda _: user)

    result = auth_service.login_user("mary", "correct-password")

    assert result is None


def test_login_user_returns_none_for_wrong_password(monkeypatch, make_user):
    user = make_user()
    user.password = security.hash_password("correct-password")

    monkeypatch.setattr(auth_service.operations, "get_user_by_nickname", lambda _: user)

    result = auth_service.login_user("mary", "wrong-password")

    assert result is None


def test_get_current_user_decodes_bearer_token_and_loads_active_user(
    monkeypatch,
    make_user,
):
    user = make_user(id="user-1")
    captured = {}

    def fake_decode_access_token(token):
        captured["token"] = token
        return {"sub": "user-1"}

    monkeypatch.setattr(auth_dependency.security, "decode_access_token", fake_decode_access_token)
    monkeypatch.setattr(
        auth_dependency.operations,
        "get_user",
        lambda user_id: user if user_id == "user-1" else None,
    )

    result = auth_dependency.get_current_user("Bearer abc.def.ghi")

    assert result is user
    assert captured["token"] == "abc.def.ghi"


@pytest.mark.parametrize("header", [None, "abc.def.ghi", "Basic abc.def.ghi"])
def test_get_current_user_rejects_missing_or_invalid_authorization_header(header):
    with pytest.raises(HTTPException) as exc_info:
        auth_dependency.get_current_user(header)

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_deleted_user(monkeypatch, make_user):
    user = make_user(user_status=constants.UserStatus.DELETED)

    monkeypatch.setattr(
        auth_dependency.security,
        "decode_access_token",
        lambda token: {"sub": "deleted-user"},
    )
    monkeypatch.setattr(auth_dependency.operations, "get_user", lambda _: user)

    with pytest.raises(HTTPException) as exc_info:
        auth_dependency.get_current_user("Bearer token")

    assert exc_info.value.status_code == 403


def test_verify_refresh_session_accepts_active_unexpired_session(monkeypatch):
    session = SimpleNamespace(
        refresh_token_hash="hash-1",
        revoked_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    monkeypatch.setattr(auth_service, "hash_token", lambda raw: "hash-1")
    monkeypatch.setattr(
        auth_service.operations,
        "get_refresh_session_by_hash_refresh_token",
        lambda token_hash: session if token_hash == "hash-1" else None,
    )

    assert auth_service.verify_refresh_session("raw-token") is session


def test_verify_refresh_session_rejects_revoked_session(monkeypatch):
    session = SimpleNamespace(
        refresh_token_hash="hash-1",
        revoked_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    monkeypatch.setattr(auth_service, "hash_token", lambda raw: "hash-1")
    monkeypatch.setattr(
        auth_service.operations,
        "get_refresh_session_by_hash_refresh_token",
        lambda _: session,
    )

    assert auth_service.verify_refresh_session("raw-token") is None
