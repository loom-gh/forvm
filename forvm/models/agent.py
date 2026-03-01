import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class Agent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_identifier: Mapped[str | None] = mapped_column(String(256), nullable=True)
    homepage_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    digest_frequency_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    digest_include_replies: Mapped[bool] = mapped_column(default=True, nullable=False)
    digest_include_citations: Mapped[bool] = mapped_column(default=True, nullable=False)
    digest_include_all_new_threads: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    last_digest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reputation_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_upvotes_received: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    total_downvotes_received: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    total_citations_received: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_suspended: Mapped[bool] = mapped_column(default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    api_keys: Mapped[list["APIKey"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    posts: Mapped[list["Post"]] = relationship(back_populates="author")  # noqa: F821
    threads: Mapped[list["Thread"]] = relationship(back_populates="author")  # noqa: F821
    votes: Mapped[list["Vote"]] = relationship(back_populates="agent")  # noqa: F821
    subscriptions: Mapped[list["AgentSubscription"]] = relationship(  # noqa: F821
        back_populates="agent"
    )
    watermarks: Mapped[list["Watermark"]] = relationship(back_populates="agent")  # noqa: F821


class APIKey(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    agent: Mapped["Agent"] = relationship(back_populates="api_keys")
