import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class ApiKeyResetToken(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "api_key_reset_tokens"

    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_used: Mapped[bool] = mapped_column(default=False, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    agent: Mapped["Agent"] = relationship(foreign_keys=[agent_id])  # noqa: F821
