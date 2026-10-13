"""add execution ownership and dispatch accounting to analysis_result

Revision ID: a1b2c3d4e5f6
Revises: 4c417c90dada
Create Date: 2026-10-13 12:00:00.000000

Phase E adds a bounded reconciler for interrupted AI analysis. Two new
concerns need durable storage on the existing analysis_result row:

* execution ownership (`execution_id`, `lease_expires_at`) so a late or
  obsolete worker can be rejected, and an abandoned RUNNING row can be
  detected without guessing from Redis.
* dispatch accounting (`dispatch_count`) so re-dispatch is observable and
  kept separate from the bounded provider budget (`attempt_count`).

Pre-existing rows: `dispatch_count` defaults to 0 and the nullable ownership
columns stay NULL. Any RUNNING row that survived the deploy has no live owner,
so its lease is set to the migration time. The reconciler then reaches a safe
terminal state for it instead of leaving it RUNNING forever.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "4c417c90dada"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_result",
        sa.Column("execution_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "analysis_result",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "analysis_result",
        sa.Column(
            "dispatch_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(
        "UPDATE analysis_result SET lease_expires_at = CURRENT_TIMESTAMP "
        "WHERE status = 'RUNNING' AND lease_expires_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("analysis_result", "dispatch_count")
    op.drop_column("analysis_result", "lease_expires_at")
    op.drop_column("analysis_result", "execution_id")
