"""add indexes used by the Stage 10 ticket query contract

Revision ID: 4f8d1b7c2a10
Revises: 996924fc3d59
Create Date: 2026-08-11 12:25:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "4f8d1b7c2a10"
down_revision: str | None = "996924fc3d59"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'TICKET_LINKED'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'TICKET_UNLINKED'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'ATTACHMENT_ADDED'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'ATTACHMENT_DELETED'")
        op.execute("ALTER TYPE entitytype ADD VALUE IF NOT EXISTS 'ATTACHMENT'")
    op.create_index(
        "ix_tickets_creator_status_created",
        "tickets",
        ["creator_user_id", "status", "created_at"],
    )
    op.create_index(
        "ix_tickets_assignee_status_updated",
        "tickets",
        ["assigned_agent_id", "status", "updated_at"],
    )
    op.create_index(
        "ix_tickets_department_status_updated",
        "tickets",
        ["department_id", "status", "updated_at"],
    )
    op.create_index("ix_tickets_deleted_due", "tickets", ["deleted_at", "due_at"])
    op.create_table(
        "ticket_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("related_ticket_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ticket_id < related_ticket_id",
            name="ck_ticket_links_canonical_order",
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["related_ticket_id"], ["tickets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", "related_ticket_id", name="uq_ticket_links_pair"),
    )
    op.create_index("ix_ticket_links_ticket", "ticket_links", ["ticket_id"])
    op.create_index(
        "ix_ticket_links_related_ticket", "ticket_links", ["related_ticket_id"]
    )
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("comment_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["comment_id"], ["comments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_attachments_comment_created",
        "attachments",
        ["comment_id", "created_at"],
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recipient_user_id", sa.String(length=36), nullable=False),
        sa.Column("notification_type", sa.String(length=60), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=True),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=180), nullable=True),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_notifications_recipient_read_created",
        "notifications",
        ["recipient_user_id", "read_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notifications_recipient_read_created",
        table_name="notifications",
    )
    op.drop_table("notifications")
    op.drop_index("ix_attachments_comment_created", table_name="attachments")
    op.drop_table("attachments")
    op.drop_index("ix_ticket_links_related_ticket", table_name="ticket_links")
    op.drop_index("ix_ticket_links_ticket", table_name="ticket_links")
    op.drop_table("ticket_links")
    op.drop_index("ix_tickets_deleted_due", table_name="tickets")
    op.drop_index("ix_tickets_department_status_updated", table_name="tickets")
    op.drop_index("ix_tickets_assignee_status_updated", table_name="tickets")
    op.drop_index("ix_tickets_creator_status_created", table_name="tickets")
