import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import UUIDMixin


class ThreadSummary(UUIDMixin, Base):
    __tablename__ = "thread_summaries"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    post_count_at_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    thread: Mapped["Thread"] = relationship(back_populates="summary")  # noqa: F821
