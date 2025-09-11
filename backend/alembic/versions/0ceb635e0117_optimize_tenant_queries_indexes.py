"""optimize_tenant_queries_indexes

Revision ID: 0ceb635e0117
Revises: f4db6466c728
Create Date: 2025-09-02 13:21:16.245701

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0ceb635e0117"
down_revision: str | Sequence[str] | None = "f4db6466c728"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add indexes to optimize tenant queries performance."""
    # Index for tenant_id on channel_instances (for counting channels by tenant)
    op.create_index(
        "ix_channel_instances_tenant_id_active",
        "channel_instances",
        ["tenant_id"],
        postgresql_where=sa.text("deleted_at IS NULL")
    )

    # Index for tenant_id on flows (for counting flows by tenant)
    op.create_index(
        "ix_flows_tenant_id_active",
        "flows",
        ["tenant_id"],
        postgresql_where=sa.text("deleted_at IS NULL")
    )

    # Composite index for tenants active status queries
    op.create_index(
        "ix_tenants_deleted_at_id",
        "tenants",
        ["deleted_at", "id"]
    )


def downgrade() -> None:
    """Remove the performance optimization indexes."""
    op.drop_index("ix_channel_instances_tenant_id_active", "channel_instances")
    op.drop_index("ix_flows_tenant_id_active", "flows")
    op.drop_index("ix_tenants_deleted_at_id", "tenants")
