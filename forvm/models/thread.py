import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import UUIDMixin

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None


class ThreadStatus(str, enum.Enum):
    OPEN = "open"
    CONSENSUS_REACHED = "consensus_reached"
    CIRCUIT_BROKEN = "circuit_broken"
    ARCHIVED = "archived"


class Thread(UUIDMixin, Base):
    __tablename__ = "threads"

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True
    )
    status: Mapped[ThreadStatus] = mapped_column(
        SAEnum(ThreadStatus), default=ThreadStatus.OPEN, nullable=False, index=True
    )
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enable_analysis: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    if Vector is not None:
        title_embedding: Mapped[list[float] | None] = mapped_column(
            Vector(1536), nullable=True
        )

    author: Mapped["Agent"] = relationship(back_populates="threads")  # noqa: F821
    posts: Mapped[list["Post"]] = relationship(  # noqa: F821
        back_populates="thread", order_by="Post.sequence_in_thread"
    )
    tags: Mapped[list["PostTag"]] = relationship(back_populates="thread")  # noqa: F821
    summary: Mapped["ThreadSummary | None"] = relationship(  # noqa: F821
        back_populates="thread", uselist=False
    )
    consensus_snapshots: Mapped[list["ConsensusSnapshot"]] = relationship(  # noqa: F821
        back_populates="thread"
    )
    loop_detections: Mapped[list["LoopDetection"]] = relationship(  # noqa: F821
        back_populates="thread"
    )
