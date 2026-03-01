"""agent_invite_provenance

Revision ID: b9a3cd5846d9
Revises: e3093d904c32
Create Date: 2026-03-01 02:02:28.619265

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9a3cd5846d9'
down_revision: Union[str, Sequence[str], None] = 'e3093d904c32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('agents', sa.Column('invite_tokens_remaining', sa.Integer(), server_default=sa.text('3'), nullable=False))
    op.add_column('agents', sa.Column('invited_by_agent_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_agents_invited_by_agent_id'), 'agents', ['invited_by_agent_id'], unique=False)
    op.create_foreign_key('fk_agents_invited_by_agent_id', 'agents', 'agents', ['invited_by_agent_id'], ['id'], ondelete='SET NULL')
    op.add_column('invite_tokens', sa.Column('created_by_agent_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_invite_tokens_created_by_agent_id'), 'invite_tokens', ['created_by_agent_id'], unique=False)
    op.create_foreign_key('fk_invite_tokens_created_by_agent_id', 'invite_tokens', 'agents', ['created_by_agent_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_invite_tokens_created_by_agent_id', 'invite_tokens', type_='foreignkey')
    op.drop_index(op.f('ix_invite_tokens_created_by_agent_id'), table_name='invite_tokens')
    op.drop_column('invite_tokens', 'created_by_agent_id')
    op.drop_constraint('fk_agents_invited_by_agent_id', 'agents', type_='foreignkey')
    op.drop_index(op.f('ix_agents_invited_by_agent_id'), table_name='agents')
    op.drop_column('agents', 'invited_by_agent_id')
    op.drop_column('agents', 'invite_tokens_remaining')
