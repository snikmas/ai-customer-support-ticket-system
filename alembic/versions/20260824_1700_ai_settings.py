"""add the global AI provider selection

Revision ID: 8d1e7b4c9a20
Revises: 4f8d1b7c2a10
Create Date: 2026-08-24 17:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision: str = "8d1e7b4c9a20"
down_revision: str | None = "4f8d1b7c2a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'AI_SETTINGS_UPDATED'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'AI_PROVIDER_TESTED'")
        op.execute("ALTER TYPE entitytype ADD VALUE IF NOT EXISTS 'AI_SETTINGS'")

    op.create_table(
        "ai_settings",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 'global'", name="ck_ai_settings_singleton"),
        sa.CheckConstraint("version > 0", name="ck_ai_settings_version_positive"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    ai_settings = sa.table(
        "ai_settings",
        sa.column("id", sa.String()),
        sa.column("provider", sa.String()),
        sa.column("model", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("updated_by_user_id", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        ai_settings,
        [{
            "id": "global",
            "provider": "fake",
            "model": "deterministic-fake-v1",
            "version": 1,
            "updated_by_user_id": None,
            "created_at": now,
            "updated_at": now,
        }],
    )


def downgrade() -> None:
    op.drop_table("ai_settings")
