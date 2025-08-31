"""Add training mode fields and flow training password

Revision ID: add_training_mode
Revises: add_flow_chat_session
Create Date: 2025-08-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_training_mode'
down_revision: Union[str, Sequence[str], None] = 'add_flow_chat_session'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add training_password to flows (encrypted LargeBinary)
    op.add_column(
        'flows',
        sa.Column('training_password', sa.LargeBinary(), nullable=True)
    )

    # Add training mode fields to chat_threads
    op.add_column(
        'chat_threads',
        sa.Column('training_mode', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.add_column(
        'chat_threads',
        sa.Column('training_mode_since', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'chat_threads',
        sa.Column('training_flow_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_chat_threads_training_flow', 'chat_threads', 'flows', ['training_flow_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    # Drop FK and columns from chat_threads
    op.drop_constraint('fk_chat_threads_training_flow', 'chat_threads', type_='foreignkey')
    op.drop_column('chat_threads', 'training_flow_id')
    op.drop_column('chat_threads', 'training_mode_since')
    op.drop_column('chat_threads', 'training_mode')

    # Drop training_password from flows
    op.drop_column('flows', 'training_password')


