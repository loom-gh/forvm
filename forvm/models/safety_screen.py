import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from forvm.database import Base


class SafetyScreenEvent(Base):
    __tablename__ = "safety_screen_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    input_type: Mapped[str] = mapped_column(String(32), nullable=False)
    safe: Mapped[bool] = mapped_column(Boolean, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    explanation: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
