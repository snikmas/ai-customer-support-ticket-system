"""add previous_refresh_token_hash for reuse detection

Revision ID: f00c00cb587a
Revises: 8d1e7b4c9a20
Create Date: 2026-09-29 15:59:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f00c00cb587a"
down_revision: str | None = "8d1e7b4c9a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "refresh_sessions",
        sa.Column("previous_refresh_token_hash", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("refresh_sessions", "previous_refresh_token_hash")
