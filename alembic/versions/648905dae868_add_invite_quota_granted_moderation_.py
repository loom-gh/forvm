"""add invite_quota_granted moderation action

Revision ID: 648905dae868
Revises: 46c599d584ac
Create Date: 2026-03-01 13:56:21.414566

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "648905dae868"
down_revision: Union[str, Sequence[str], None] = "46c599d584ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'INVITE_QUOTA_GRANTED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing enum values.
