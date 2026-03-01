"""add welcome email support

Revision ID: f85cf2dae8c1
Revises: c3c1ec3080bf
Create Date: 2026-03-01 11:23:21.687178

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f85cf2dae8c1"
down_revision: Union[str, Sequence[str], None] = "c3c1ec3080bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "agents",
        sa.Column(
            "welcome_sent", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'welcome'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("agents", "welcome_sent")
    # Note: PostgreSQL does not support removing enum values.
