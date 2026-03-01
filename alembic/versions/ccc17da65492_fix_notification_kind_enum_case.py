"""fix notification_kind enum case

Revision ID: ccc17da65492
Revises: f85cf2dae8c1
Create Date: 2026-03-01 11:44:38.489059

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ccc17da65492"
down_revision: Union[str, Sequence[str], None] = "f85cf2dae8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add uppercase enum values to match PgEnum .name serialization.

    Prior migrations added lowercase values ('thread_digest', 'digest',
    'welcome') but SQLAlchemy PgEnum persists the Python enum .name
    (uppercase). The lowercase values remain but are unused.
    """
    op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'THREAD_DIGEST'")
    op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'DIGEST'")
    op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'WELCOME'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing enum values.
