import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from forvm.database import Base
from forvm.models.mixins import UUIDMixin


class DigestEntry(UUIDMixin, Base):
    __tablename__ = "digest_entries"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    thread_highlights: Mapped[list] = mapped_column(JSONB, default=list)
    new_post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
