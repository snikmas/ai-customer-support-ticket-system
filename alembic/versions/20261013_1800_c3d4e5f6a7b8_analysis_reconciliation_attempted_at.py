"""add durable reconciliation fairness marker to analysis_result

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-13 18:00:00.000000

The bounded analysis reconciler always fetched the same oldest page. While an
older PENDING row still had a live queued/scheduled RQ job it was repeatedly
returned as ``left_live`` and a later PENDING row with no job was never reached.

``reconciliation_attempted_at`` records the last pass that considered a row.
The scan orders it NULLS FIRST (never considered first), so a live row rotates
behind never-considered and older-considered rows instead of occupying the
first page forever. With ``W`` recoverable rows and batch size ``B`` a stable
set is fully visited once per ``ceil(W / B)`` passes -- the finite recovery
bound. The marker is durable on the row, so progress survives a restart and
needs no in-memory cursor.

Pre-existing rows keep a NULL marker, meaning "never considered", so they are
scanned first after the upgrade.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_result",
        sa.Column(
            "reconciliation_attempted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_analysis_result_reconciliation_scan",
        "analysis_result",
        ["status", "reconciliation_attempted_at", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_result_reconciliation_scan",
        table_name="analysis_result",
    )
    op.drop_column("analysis_result", "reconciliation_attempted_at")
