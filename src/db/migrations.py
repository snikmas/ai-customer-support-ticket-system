from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def add_agent_profile_last_assigned_at(engine: Engine) -> None:

    inspector = inspect(engine)
    if "agent_profiles" not in inspector.get_table_names():
        return
    column_names = {
        column["name"] for column in inspector.get_columns("agent_profiles")
    }
    if "last_assigned_at" in column_names:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE agent_profiles ADD COLUMN last_assigned_at DATETIME")
        )


def add_ticket_due_at(engine: Engine) -> None:
    """Add the nullable stage deadline to an existing database once."""
    inspector = inspect(engine)
    if "tickets" not in inspector.get_table_names():
        return
    column_names = {
        column["name"] for column in inspector.get_columns("tickets")
    }
    if "due_at" in column_names:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tickets ADD COLUMN due_at DATETIME"))


def add_ticket_department_id(engine: Engine) -> None:
    """Keep existing tickets valid while new writes require a department."""
    inspector = inspect(engine)
    if "tickets" not in inspector.get_table_names():
        return
    column_names = {column["name"] for column in inspector.get_columns("tickets")}
    if "department_id" in column_names:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE tickets ADD COLUMN department_id VARCHAR(36)")
        )


def backfill_legacy_departments(engine: Engine) -> None:
    """Turn old free-form profile department IDs into active catalog rows."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not {"agent_profiles", "departments"}.issubset(tables):
        return

    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as connection:
        legacy_ids = list(connection.execute(
            text(
                "SELECT DISTINCT department_id FROM agent_profiles "
                "WHERE department_id IS NOT NULL"
            )
        ).scalars())
        for department_id in legacy_ids:
            existing = connection.execute(
                text("SELECT 1 FROM departments WHERE id = :id"),
                {"id": department_id},
            ).scalar_one_or_none()
            if existing is not None:
                continue

            normalized_name = " ".join(str(department_id).casefold().split())
            same_name_id = connection.execute(
                text(
                    "SELECT id FROM departments "
                    "WHERE normalized_name = :normalized_name"
                ),
                {"normalized_name": normalized_name},
            ).scalar_one_or_none()
            if same_name_id is not None:
                connection.execute(
                    text(
                        "UPDATE agent_profiles SET department_id = :canonical_id "
                        "WHERE department_id = :legacy_id"
                    ),
                    {
                        "canonical_id": same_name_id,
                        "legacy_id": department_id,
                    },
                )
                continue

            connection.execute(
                text(
                    "INSERT INTO departments "
                    "(id, name, normalized_name, description, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :name, :normalized_name, NULL, :created_at, :updated_at, NULL)"
                ),
                {
                    "id": department_id,
                    "name": department_id,
                    "normalized_name": normalized_name,
                    "created_at": now,
                    "updated_at": now,
                },
            )


def migrate_event_actor_contract(engine: Engine) -> None:
    """Add explicit human/system actors and overdue-event idempotency."""
    inspector = inspect(engine)
    if "events" not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns("events")}
    already_current = (
        "actor_type" in columns
        and "idempotency_key" in columns
        and columns["actor_user_id"]["nullable"]
    )
    if already_current:
        return

    if engine.dialect.name != "sqlite":
        with engine.begin() as connection:
            if "actor_type" not in columns:
                connection.execute(text(
                    "ALTER TABLE events ADD COLUMN actor_type VARCHAR(6) "
                    "NOT NULL DEFAULT 'HUMAN'"
                ))
            if "idempotency_key" not in columns:
                connection.execute(text(
                    "ALTER TABLE events ADD COLUMN idempotency_key VARCHAR(100)"
                ))
                connection.execute(text(
                    "CREATE UNIQUE INDEX uq_events_idempotency_key "
                    "ON events (idempotency_key)"
                ))
            connection.execute(text(
                "ALTER TABLE events ALTER COLUMN actor_user_id DROP NOT NULL"
            ))
        return

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        with connection.begin():
            connection.exec_driver_sql("DROP TABLE IF EXISTS events__actor_migration")
            connection.exec_driver_sql(
                """
                CREATE TABLE events__actor_migration (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    entity_type VARCHAR(32) NOT NULL,
                    entity_id VARCHAR(36),
                    actor_type VARCHAR(6) NOT NULL DEFAULT 'HUMAN',
                    actor_user_id VARCHAR(36),
                    event_type VARCHAR(40) NOT NULL,
                    old_value TEXT,
                    batch_id VARCHAR(36),
                    new_value TEXT NOT NULL,
                    metadata VARCHAR(200),
                    idempotency_key VARCHAR(100),
                    created_at DATETIME NOT NULL,
                    CONSTRAINT ck_events_actor_contract CHECK (
                        (actor_type = 'HUMAN' AND actor_user_id IS NOT NULL) OR
                        (actor_type = 'SYSTEM' AND actor_user_id IS NULL)
                    ),
                    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT,
                    UNIQUE (idempotency_key)
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO events__actor_migration (
                    id, entity_type, entity_id, actor_type, actor_user_id,
                    event_type, old_value, batch_id, new_value, metadata,
                    idempotency_key, created_at
                )
                SELECT
                    id, entity_type, entity_id, 'HUMAN', actor_user_id,
                    event_type, old_value, batch_id, new_value, metadata,
                    NULL, created_at
                FROM events
                """
            )
            connection.exec_driver_sql("DROP TABLE events")
            connection.exec_driver_sql(
                "ALTER TABLE events__actor_migration RENAME TO events"
            )
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


def migrate_analysis_result_contract(engine: Engine) -> None:
    """Rebuild the unfinished legacy analysis table into its durable contract."""
    inspector = inspect(engine)
    if "analysis_result" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("analysis_result")}
    lifecycle_columns = {
        "input_snapshot",
        "summary",
        "error_code",
        "error_message",
        "ticket_id",
        "job_id",
        "requester_id",
        "attempt_count",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
        "status",
    }
    provenance_columns = {
        "provider": "VARCHAR(30)",
        "model": "VARCHAR(100)",
        "prompt_version": "VARCHAR(50)",
        "input_tokens": "INTEGER",
        "output_tokens": "INTEGER",
    }
    lifecycle_current = (
        lifecycle_columns.issubset(columns)
        and columns["ticket_id"]["nullable"]
        and columns["requester_id"]["nullable"]
        and columns["job_id"]["nullable"]
        and columns["summary"]["nullable"]
    )
    if lifecycle_current:
        missing_provenance = [
            (name, sql_type)
            for name, sql_type in provenance_columns.items()
            if name not in columns
        ]
        if missing_provenance:
            with engine.begin() as connection:
                for name, sql_type in missing_provenance:
                    connection.execute(text(
                        f"ALTER TABLE analysis_result ADD COLUMN {name} {sql_type}"
                    ))
        return
    if engine.dialect.name != "sqlite":
        raise RuntimeError(
            "Existing non-SQLite analysis_result tables require a managed migration"
        )

    legacy_snapshot = (
        '{"title":"Legacy analysis","description":"Input snapshot unavailable",'
        '"category":"Account Access","tags":[],"priority":2,"status":"New"}'
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        with connection.begin():
            connection.exec_driver_sql(
                "DROP TABLE IF EXISTS analysis_result__contract_migration"
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE analysis_result__contract_migration (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    input_snapshot TEXT NOT NULL,
                    summary VARCHAR(300),
                    error_code VARCHAR(50),
                    error_message VARCHAR(255),
                    ticket_id VARCHAR(36),
                    job_id VARCHAR(100),
                    requester_id VARCHAR(36),
                    provider VARCHAR(30),
                    model VARCHAR(100),
                    prompt_version VARCHAR(50),
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    started_at DATETIME,
                    completed_at DATETIME,
                    updated_at DATETIME NOT NULL,
                    status VARCHAR(9) NOT NULL,
                    CONSTRAINT ck_analysis_result_attempt_count
                        CHECK (attempt_count >= 0 AND attempt_count <= 3),
                    CONSTRAINT ck_analysis_result_lifecycle CHECK (
                        (
                            status = 'PENDING'
                            AND summary IS NULL
                            AND error_code IS NULL
                            AND error_message IS NULL
                            AND completed_at IS NULL
                            AND attempt_count < 3
                        )
                        OR (
                            status = 'RUNNING'
                            AND summary IS NULL
                            AND error_code IS NULL
                            AND error_message IS NULL
                            AND started_at IS NOT NULL
                            AND completed_at IS NULL
                            AND attempt_count BETWEEN 1 AND 3
                        )
                        OR (
                            status = 'COMPLETED'
                            AND summary IS NOT NULL
                            AND error_code IS NULL
                            AND error_message IS NULL
                            AND started_at IS NOT NULL
                            AND completed_at IS NOT NULL
                            AND attempt_count BETWEEN 1 AND 3
                        )
                        OR (
                            status = 'FAILED'
                            AND summary IS NULL
                            AND error_code IS NOT NULL
                            AND error_message IS NOT NULL
                            AND completed_at IS NOT NULL
                        )
                    ),
                    FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE SET NULL,
                    FOREIGN KEY(requester_id) REFERENCES users (id) ON DELETE SET NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO analysis_result__contract_migration (
                    id, input_snapshot, summary, error_code, error_message,
                    ticket_id, job_id, requester_id, provider, model,
                    prompt_version, input_tokens, output_tokens, attempt_count, created_at,
                    started_at, completed_at, updated_at, status
                )
                SELECT
                    id, ?, NULL, 'legacy_contract_migrated',
                    'Legacy analysis could not be resumed',
                    ticket_id, job_id, requester_id, NULL, NULL,
                    NULL, NULL, NULL, 0, created_at,
                    NULL, created_at, created_at, 'FAILED'
                FROM analysis_result
                """,
                (legacy_snapshot,),
            )
            connection.exec_driver_sql("DROP TABLE analysis_result")
            connection.exec_driver_sql(
                "ALTER TABLE analysis_result__contract_migration RENAME TO analysis_result"
            )
            connection.exec_driver_sql(
                """
                CREATE UNIQUE INDEX uq_analysis_result_active_ticket
                ON analysis_result (ticket_id)
                WHERE ticket_id IS NOT NULL AND status IN ('PENDING', 'RUNNING')
                """
            )
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
