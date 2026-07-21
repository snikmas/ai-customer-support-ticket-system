from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import bcrypt
import pytest
from src import constants
from src.core import security
from src.dependencies import auth as auth_dependency
from src.services import auth as auth_service
from src.models import LoginRequest
from pydantic import ValidationError
from src.exceptions import AuthenticationError, InactiveUserError, InvalidCredentialsError, RefreshSessionRevokedError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.db import models as db_models
from src.db import operations


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
        return {"sub": "user-1", "type": "access"}

    monkeypatch.setattr(auth_dependency.security, "decode_access_token", fake_decode_access_token)
    monkeypatch.setattr(
        auth_dependency.operations,
        "get_user",
        lambda user_id: user if user_id == "user-1" else None,
    )

    result = auth_dependency.get_current_user("Bearer abc.def.ghi")

    assert result is user
    assert captured["token"] == "abc.def.ghi"


@pytest.mark.parametrize("payload", [{}, {"type": "access"}, {"sub": "user-1"}, {"sub": "user-1", "type": "refresh"}])
def test_get_current_user_rejects_missing_claims_and_wrong_token_type(monkeypatch, payload):
    monkeypatch.setattr(auth_dependency.security, "decode_access_token", lambda _: payload)
    monkeypatch.setattr(
        auth_dependency.operations,
        "get_user",
        lambda _: pytest.fail("invalid payload must be rejected before a database lookup"),
    )

    with pytest.raises(InvalidCredentialsError) as exc_info:
        auth_dependency.get_current_user("Bearer token")

    assert exc_info.value.status_code == 401


@pytest.mark.parametrize(
    "data",
    [
        {"password": "valid-password"},
        {"nickname": "mary", "email": "mary@example.com", "password": "valid-password"},
    ],
)
def test_login_request_requires_exactly_one_identifier(data):
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(data)


@pytest.mark.parametrize("header", [None, "abc.def.ghi", "Basic abc.def.ghi"])
def test_get_current_user_rejects_missing_or_invalid_authorization_header(header):
    with pytest.raises(AuthenticationError) as exc_info:
        auth_dependency.get_current_user(header)

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_deleted_user(monkeypatch, make_user):
    user = make_user(user_status=constants.UserStatus.DELETED)

    monkeypatch.setattr(
        auth_dependency.security,
        "decode_access_token",
        lambda token: {"sub": "deleted-user", "type": "access"},
    )
    monkeypatch.setattr(auth_dependency.operations, "get_user", lambda _: user)

    with pytest.raises(InactiveUserError) as exc_info:
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

    with pytest.raises(RefreshSessionRevokedError):
        auth_service.verify_refresh_session("raw-token")


def test_refresh_rotation_rejects_a_second_use_of_the_same_session_snapshot(monkeypatch, make_user):
    user = make_user(id="user-1")
    stale_session = SimpleNamespace(id="session-1", user_id=user.id, refresh_token_hash="old-hash")
    stored_hash = {"value": "old-hash"}
    generated_tokens = iter(["first-new-token", "second-new-token"])

    monkeypatch.setattr(auth_service.operations, "get_user", lambda _: user)
    monkeypatch.setattr(auth_service, "create_access_token", lambda _: "new-access-token")
    monkeypatch.setattr(auth_service, "generate_refresh_token", lambda: next(generated_tokens))
    monkeypatch.setattr(auth_service, "hash_token", lambda raw: f"hash:{raw}")

    def conditional_rotate(session_id, *, current_hash, hash_ref_token, **kwargs):
        if session_id != stale_session.id or stored_hash["value"] != current_hash:
            return None
        stored_hash["value"] = hash_ref_token
        return stale_session

    monkeypatch.setattr(auth_service.operations, "rotate_refresh_session", conditional_rotate)

    first_response = auth_service.rotate_refresh_session(stale_session)
    second_response = auth_service.rotate_refresh_session(stale_session)

    assert first_response.refresh_token == "first-new-token"
    assert second_response is None


def test_refresh_session_expiry_remains_utc_aware_after_sqlite_round_trip(
    monkeypatch,
    tmp_path,
):
    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'refresh.db'}")
    db_models.Base.metadata.create_all(test_engine)
    monkeypatch.setattr(operations, "engine", test_engine)
    now = datetime.now(timezone.utc)

    with Session(test_engine) as session, session.begin():
        session.add(
            db_models.User(
                id="refresh-user",
                nickname="refresh-user",
                avatar_url=None,
                first_name="Refresh",
                last_name="User",
                phone="+15550200",
                email="refresh-user@example.com",
                password="already-hashed",
                role=constants.Role.USER,
                user_status=constants.UserStatus.ACTIVE,
                updated_at=now,
                created_at=now,
            )
        )
        session.flush()
        session.add(
            db_models.RefreshSession(
                id="refresh-session",
                user_id="refresh-user",
                refresh_token_hash="stored-hash",
                expires_at=now + timedelta(days=1),
                revoked_at=None,
                created_at=now,
            )
        )

    loaded = operations.get_refresh_session_by_id("refresh-session")

    assert loaded.expires_at.tzinfo is not None
    assert loaded.expires_at.utcoffset() == timedelta(0)
