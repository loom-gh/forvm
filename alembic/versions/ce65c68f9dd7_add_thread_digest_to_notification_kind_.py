"""add thread_digest to notification_kind enum

Revision ID: ce65c68f9dd7
Revises: a22e136b63c4
Create Date: 2026-03-01 00:08:22.778427

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ce65c68f9dd7"
down_revision: Union[str, Sequence[str], None] = "a22e136b63c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'thread_digest'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing values from enums.
    pass
