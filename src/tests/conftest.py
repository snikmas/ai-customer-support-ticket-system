from datetime import datetime, timezone
from types import SimpleNamespace
import os
import uuid

import pytest
from sqlalchemy import create_engine, event

from main import app
from src import constants
from src.db import models as db_models
from src.db import operations as db_operations


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def synthetic_refresh_token_secret(monkeypatch):
    """Provide a synthetic refresh-token secret for every test.

    Refresh-session tests build tokens through ``src.core.security.hash_token``,
    which requires ``REFRESH_TOKEN_SECRET``. The release verifier deliberately
    strips any inherited real secret, so the suite must supply its own. This is
    a fixed synthetic value, never a developer or production secret.
    """
    monkeypatch.setenv("REFRESH_TOKEN_SECRET", "test-refresh-token-secret")


@pytest.fixture(scope="session", autouse=True)
def synthetic_jwt_keys():
    """Provide disposable RS256 keys for the whole test session.

    ``src/core/security`` defaults to the project ``keys/`` directory, which is
    a developer's untracked files and is absent from a clean checkout or release
    package. Generating a throwaway key pair here keeps the suite self-contained:
    it never reads a developer key, and it runs from the packaged source.
    """
    import tempfile
    from pathlib import Path

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from src.core import security

    key_dir = Path(tempfile.mkdtemp(prefix="resolveai-test-jwt-"))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = key_dir / "private.pem"
    public_path = key_dir / "public.pem"
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    os.environ["JWT_PRIVATE_KEY_PATH"] = str(private_path)
    os.environ["JWT_PUBLIC_KEY_PATH"] = str(public_path)
    os.environ["JWT_ALGORITHM"] = "RS256"
    security._JWT_KEY_CACHE.clear()
    yield
    for name in ("JWT_PRIVATE_KEY_PATH", "JWT_PUBLIC_KEY_PATH", "JWT_ALGORITHM"):
        os.environ.pop(name, None)
    security._JWT_KEY_CACHE.clear()


@pytest.fixture(scope="session")
def task_owned_postgres_url():
    """Create a PostgreSQL database owned by this test run, then drop it.

    ``TEST_POSTGRES_URL`` is treated as a server address: the run creates a
    uniquely named database on it and removes it at session end. Ownership is a
    fact of this run creating the database, so an inherited or wrong URL can no
    longer pass just because it is reachable.
    """
    from src.tests import pg_target

    base_url = os.getenv(pg_target.BASE_URL_ENV)
    if not base_url:
        pytest.skip("TEST_POSTGRES_URL is not set")
    if os.getenv(pg_target.OPT_IN_ENV) != "1":
        pytest.skip(
            f"{pg_target.OPT_IN_ENV}=1 is required to run the destructive "
            "PostgreSQL integration fixture"
        )

    token = f"{os.getpid()}_{uuid.uuid4().hex[:12]}"
    plan = pg_target.plan_task_owned_target(base_url, token=token)
    pg_target.create_task_owned_database(plan)
    try:
        yield plan.owned_url
    finally:
        pg_target.drop_task_owned_database(plan)


@pytest.fixture
def make_user():
    def _make_user(
        *,
        id="user-1",
        nickname="test-user",
        role=constants.Role.USER,
        user_status=constants.UserStatus.ACTIVE,
    ):
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=id,
            nickname=nickname,
            avatar_url=None,
            first_name="Test",
            last_name="User",
            phone=f"phone-{id}",
            email=f"{id}@example.com",
            role=role,
            password="hashed-password",
            updated_at=now,
            created_at=now,
            due_at=None,
            deleted_at=None,
            user_status=user_status,
        )

    return _make_user


@pytest.fixture
def make_ticket():
    def _make_ticket(
        *,
        id="ticket-1",
        creator_user_id="user-1",
        assigned_agent_id=None,
        status=constants.Status.NEW,
        priority=constants.Priority.NORMAL,
        tags=None,
    ):
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=id,
            title="Test ticket",
            description="Test description",
            category=constants.Category.ACCOUNT_ACCESS,
            tags=tags if tags is not None else [constants.Tag.API_KEY],
            department_id="support",
            skill_ids=[],
            assigned_agent_id=assigned_agent_id,
            creator_user_id=creator_user_id,
            status=status,
            priority=priority,
            updated_at=now,
            created_at=now,
            due_at=None,
            deleted_at=None,
        )

    return _make_ticket


def _sqlite_test_engine(path):
    engine = create_engine(
        f"sqlite+pysqlite:///{path}",
        connect_args={"timeout": 15},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _postgres_test_engine(url):
    # Explicit timeouts turn a would-be deadlock into a clear test failure
    # instead of a hung suite.
    return create_engine(
        url,
        connect_args={
            "options": "-c lock_timeout=5000 -c statement_timeout=20000",
        },
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )


@pytest.fixture(params=["sqlite", "postgres"])
def mutation_engine(request, tmp_path, monkeypatch):
    """A fresh empty database on each engine for ticket-mutation concurrency.

    PostgreSQL is used only when TEST_POSTGRES_URL is set; otherwise it skips
    cleanly and the SQLite variant still runs. Separate sessions/connections
    are opened by the tests, and the app's operations layer is pointed at the
    isolated engine.
    """
    if request.param == "postgres":
        url = request.getfixturevalue("task_owned_postgres_url")
        engine = _postgres_test_engine(url)
    else:
        engine = _sqlite_test_engine(tmp_path / "ticket-mutation.db")

    db_models.Base.metadata.drop_all(engine)
    db_models.Base.metadata.create_all(engine)
    monkeypatch.setattr(db_operations, "engine", engine)
    yield engine
    engine.dispose()
