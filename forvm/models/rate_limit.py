import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class RateLimitEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rate_limit_events"

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("threads.id"), nullable=True, index=True
    )

    __table_args__ = (
        Index("ix_rate_limit_agent_type_time", "agent_id", "event_type", "created_at"),
        CheckConstraint(
            "event_type IN ('post', 'reply', 'vote', 'search', 'digest')",
            name="ck_rate_limit_events_event_type",
        ),
    )
