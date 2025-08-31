"""Add FlowChatSession table for chat clearing functionality

Revision ID: 20250124_add_flow_chat_session_table
Revises: 
Create Date: 2025-01-24

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_flow_chat_session"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add FlowChatSession table for tracking chat clear timestamps."""
    # Create the flow_chat_sessions table
    op.create_table(
        "flow_chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["flow_id"], ["flows.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("flow_id", name="uq_flow_chat_sessions_flow_id")
    )


def downgrade() -> None:
    """Remove FlowChatSession table."""
    op.drop_table("flow_chat_sessions")
