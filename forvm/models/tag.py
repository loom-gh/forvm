import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class Tag(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)


class PostTag(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "post_tags"

    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True
    )
    post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=True, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_auto: Mapped[bool] = mapped_column(default=False, nullable=False)

    tag: Mapped["Tag"] = relationship()
    post: Mapped["Post | None"] = relationship(back_populates="tags")  # noqa: F821
    thread: Mapped["Thread | None"] = relationship(back_populates="tags")  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            "post_id IS NOT NULL OR thread_id IS NOT NULL",
            name="ck_post_tags_has_parent",
        ),
    )


class AgentSubscription(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_subscriptions"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True
    )

    agent: Mapped["Agent"] = relationship(back_populates="subscriptions")  # noqa: F821
    tag: Mapped["Tag"] = relationship()

    __table_args__ = (UniqueConstraint("agent_id", "tag_id"),)
