import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class ConsensusSnapshot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "consensus_snapshots"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consensus_score: Mapped[float] = mapped_column(Float, nullable=False)
    synthesis_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    participating_agent_ids: Mapped[list] = mapped_column(JSONB, default=list)
    key_agreements: Mapped[list] = mapped_column(JSONB, default=list)
    remaining_disagreements: Mapped[list] = mapped_column(JSONB, default=list)
    post_count_at_analysis: Mapped[int] = mapped_column(Integer, nullable=False)

    thread: Mapped["Thread"] = relationship(back_populates="consensus_snapshots")  # noqa: F821


class LoopDetection(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "loop_detections"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    involved_agent_ids: Mapped[list] = mapped_column(JSONB, default=list)
    loop_description: Mapped[str] = mapped_column(Text, nullable=False)
    action_taken: Mapped[str] = mapped_column(String(32), nullable=False)
    post_window_start: Mapped[int] = mapped_column(Integer, nullable=False)
    post_window_end: Mapped[int] = mapped_column(Integer, nullable=False)

    thread: Mapped["Thread"] = relationship(back_populates="loop_detections")  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            "action_taken IN ('warned', 'throttled', 'circuit_broken')",
            name="ck_loop_detections_action_taken",
        ),
    )
