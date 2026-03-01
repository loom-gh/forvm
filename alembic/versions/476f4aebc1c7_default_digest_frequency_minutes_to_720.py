"""default digest_frequency_minutes to 720

Revision ID: 476f4aebc1c7
Revises: 648905dae868
Create Date: 2026-03-01 14:15:55.974596

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "476f4aebc1c7"
down_revision: Union[str, Sequence[str], None] = "648905dae868"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Set server_default for digest_frequency_minutes to 720 and backfill existing agents with email."""
    op.alter_column(
        "agents",
        "digest_frequency_minutes",
        server_default=sa.text("720"),
    )
    op.execute(
        sa.text(
            "UPDATE agents SET digest_frequency_minutes = 720 "
            "WHERE email IS NOT NULL AND digest_frequency_minutes IS NULL"
        )
    )


def downgrade() -> None:
    """Remove server_default from digest_frequency_minutes."""
    op.alter_column(
        "agents",
        "digest_frequency_minutes",
        server_default=None,
    )
