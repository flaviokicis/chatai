"""Drop thought tracing tables - using Langfuse for observability

Revision ID: 190180b9a510
Revises: 1e2c0e3c4626
Create Date: 2025-09-10 19:52:23.687310

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "190180b9a510"
down_revision: str | Sequence[str] | None = "1e2c0e3c4626"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop thought tracing tables - replaced by Langfuse observability."""
    # Drop agent_thoughts table first (has foreign key to agent_conversation_traces)
    op.drop_table("agent_thoughts")

    # Drop agent_conversation_traces table
    op.drop_table("agent_conversation_traces")


def downgrade() -> None:
    """Recreate thought tracing tables (not recommended - use Langfuse instead)."""
    # Note: This downgrade recreates the tables but they won't have data
    # and the application code no longer supports them.
    # This is only for emergency rollback scenarios.

    # Recreate agent_conversation_traces table
    op.create_table("agent_conversation_traces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),  # EncryptedString
        sa.Column("session_id", sa.String(255), nullable=True),
        sa.Column("agent_type", sa.String(100), nullable=False),
        sa.Column("channel_id", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_thoughts", sa.Integer(), nullable=True, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", "agent_type", name="uq_trace_per_user_agent")
    )

    # Create indexes for agent_conversation_traces
    op.create_index("ix_trace_tenant_user", "agent_conversation_traces", ["tenant_id", "user_id"])
    op.create_index("ix_trace_last_activity", "agent_conversation_traces", ["last_activity_at"])

    # Recreate agent_thoughts table
    op.create_table("agent_thoughts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_trace_id", sa.UUID(), nullable=False),
        sa.Column("user_message", sa.String(), nullable=False),  # EncryptedString
        sa.Column("current_state", sa.JSON(), nullable=True),
        sa.Column("available_tools", sa.JSON(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("selected_tool", sa.String(100), nullable=False),
        sa.Column("tool_args", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("tool_result", sa.Text(), nullable=True),
        sa.Column("agent_response", sa.String(), nullable=True),  # EncryptedString
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=False, default="unknown"),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_trace_id"], ["agent_conversation_traces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id")
    )

    # Create indexes for agent_thoughts
    op.create_index("ix_thought_trace_timestamp", "agent_thoughts", ["conversation_trace_id", "created_at"])
    op.create_index("ix_thought_tool_name", "agent_thoughts", ["selected_tool"])
