import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class InviteToken(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "invite_tokens"

    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_used: Mapped[bool] = mapped_column(default=False, nullable=False)
    used_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )

    used_by_agent: Mapped["Agent | None"] = relationship(  # noqa: F821
        foreign_keys=[used_by_agent_id]
    )
    created_by_agent: Mapped["Agent | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_agent_id]
    )
