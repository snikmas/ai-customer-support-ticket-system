"""Task-owned PostgreSQL integration targets.

The concurrency fixtures run ``Base.metadata.drop_all``. A URL alone does not
prove a database is disposable: it can be inherited from a developer shell or
point at a real database. The earlier isolation check required only
``TEST_POSTGRES_ALLOW_DESTRUCTIVE=1`` plus ``SELECT 1``, which proves the target
is reachable -- not that this test run owns it.

Instead, the run creates its own uniquely named database on the server that
``TEST_POSTGRES_URL`` addresses and drops it afterwards. Ownership then follows
from this run creating the database, never from the database name or the host
address. The configured database is used only as a connection anchor for
``CREATE DATABASE`` and is never dropped by this module.

The helpers are import-safe without a server: ``plan_task_owned_target`` and
``require_opt_in`` perform no I/O, so rejection can be tested against synthetic
configuration without contacting any service.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

OPT_IN_ENV = "TEST_POSTGRES_ALLOW_DESTRUCTIVE"
BASE_URL_ENV = "TEST_POSTGRES_URL"

# Every database this run creates carries this prefix so a leaked database is
# obvious in ``\l`` output, but the name is never trusted as proof of ownership.
_DATABASE_PREFIX = "resolveai_test_"


class UnsafeIntegrationTargetError(RuntimeError):
    """Raised when an integration target cannot be proven task-owned."""


@dataclass(frozen=True)
class TaskOwnedPostgres:
    """A run-owned database derived from the configured server URL."""

    base_url: str
    database: str
    owned_url: str


def require_opt_in(env: dict[str, str] | None = None) -> None:
    """Refuse an integration target unless destructive setup is explicitly asked.

    No connection is made: this is a pure configuration gate.
    """
    values = os.environ if env is None else env
    if values.get(OPT_IN_ENV) != "1":
        raise UnsafeIntegrationTargetError(
            f"{OPT_IN_ENV}=1 is required before the destructive PostgreSQL "
            "integration fixture may run"
        )


def task_owned_database_name(token: str) -> str:
    """Return a safe, run-unique database name for the given token."""
    normalized = re.sub(r"[^a-z0-9_]", "_", token.lower()).strip("_")
    if not normalized:
        raise UnsafeIntegrationTargetError("A non-empty run token is required")
    # PostgreSQL identifiers are limited to 63 bytes; keep the prefix visible.
    return f"{_DATABASE_PREFIX}{normalized}"[:63]


def plan_task_owned_target(base_url: str, *, token: str) -> TaskOwnedPostgres:
    """Validate the server URL and derive a fresh owned database. No I/O.

    Raises ``UnsafeIntegrationTargetError`` for anything that is not a
    PostgreSQL server URL with a database to connect through, so a wrong or
    inherited target fails clearly before any schema work.
    """
    try:
        url = make_url(base_url)
    except Exception as exc:  # pragma: no cover - sqlalchemy message varies
        raise UnsafeIntegrationTargetError(
            f"TEST_POSTGRES_URL is not a usable URL: {exc}"
        ) from exc

    if url.get_backend_name() != "postgresql":
        raise UnsafeIntegrationTargetError(
            "TEST_POSTGRES_URL must be a PostgreSQL URL; refusing to run the "
            "destructive fixture against another dialect"
        )
    if not url.database or url.database.strip() == "":
        raise UnsafeIntegrationTargetError(
            "TEST_POSTGRES_URL must name a database to connect through (the "
            "anchor connection for CREATE DATABASE)"
        )
    # Reject an unqualified network host that could be a shared production host
    # when the caller has not opted into disposable targets. Ownership of the
    # created database is still the real guarantee; this makes the anchor URL
    # explicit.
    if urlsplit(base_url).hostname is None and url.host is None:
        raise UnsafeIntegrationTargetError(
            "TEST_POSTGRES_URL must include a host"
        )

    database = task_owned_database_name(token)
    owned_url = url.set(database=database).render_as_string(hide_password=False)
    return TaskOwnedPostgres(
        base_url=base_url,
        database=database,
        owned_url=owned_url,
    )


def create_task_owned_database(plan: TaskOwnedPostgres) -> None:
    """Create the run-owned database. ``CREATE DATABASE`` cannot run in a txn."""
    engine = create_engine(plan.base_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{plan.database}"'))
            connection.execute(text(f'CREATE DATABASE "{plan.database}"'))
    finally:
        engine.dispose()


def drop_task_owned_database(plan: TaskOwnedPostgres) -> None:
    """Drop the run-owned database, forcing any leftover connections closed."""
    engine = create_engine(plan.base_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{plan.database}" WITH (FORCE)')
            )
    finally:
        engine.dispose()
