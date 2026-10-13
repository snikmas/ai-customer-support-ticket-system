"""add durable routing attempt time and fair-scan index to tickets

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-13 16:00:00.000000

Phase G makes routing reconciliation fair. The old scanner always fetched the
same oldest page, so a ticket behind more than one batch of unassignable
tickets was never selected.

``routing_attempted_at`` records the last reconciliation pass that dispatched a
ticket. The fair scan orders it NULLS FIRST (never attempted first), so a ticket
that cannot be assigned now rotates behind the rest. The timestamp is durable on
the row, so progress survives a process restart and needs no in-memory cursor.

``ix_tickets_waiting_scan`` supports the waiting predicate plus the new
least-recently-attempted ordering. Existing rows keep a NULL attempt time, which
means "never attempted", so they are considered first after the upgrade.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "routing_attempted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_tickets_waiting_scan",
        "tickets",
        [
            "deleted_at",
            "status",
            "assigned_agent_id",
            "routing_attempted_at",
            "created_at",
            "id",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_waiting_scan", table_name="tickets")
    op.drop_column("tickets", "routing_attempted_at")
