"""Alembic migration environment.

Alembic loads this module for every command (`upgrade`, `downgrade`,
`revision --autogenerate`). Its two jobs:

1. Tell Alembic WHICH database to talk to — the same DATABASE_URL the app
   uses (src.core.config), so migrations and the application can never point
   at different databases by accident.
2. Tell Alembic WHAT the schema should look like — the SQLAlchemy metadata
   assembled from src/db/models.py. Autogenerate diffs the live database
   against this metadata and writes the difference as a migration.
"""

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic runs as a console script, so the project root is not automatically
# importable (sys.path[0] is the venv's bin/ directory, not the CWD). Put the
# repository root on sys.path so `src` imports work regardless of where the
# command is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import DATABASE_URL
from src.db.models import Base

config = context.config

# Inject the application's URL into Alembic's config at runtime.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without connecting (used for review: `alembic upgrade head --sql`)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations directly."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
