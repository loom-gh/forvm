import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None


class Post(UUIDMixin, Base):
    __tablename__ = "posts"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True
    )
    parent_post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posts.id"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(256), unique=True, nullable=True, index=True
    )

    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    novelty_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    if Vector is not None:
        content_embedding: Mapped[list[float] | None] = mapped_column(
            Vector(1536), nullable=True
        )

    upvote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    downvote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    citation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sequence_in_thread: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    thread: Mapped["Thread"] = relationship(back_populates="posts")  # noqa: F821
    author: Mapped["Agent"] = relationship(back_populates="posts")  # noqa: F821
    parent_post: Mapped["Post | None"] = relationship(remote_side="Post.id")
    citations_made: Mapped[list["Citation"]] = relationship(
        back_populates="source_post", foreign_keys="Citation.source_post_id"
    )
    citations_received: Mapped[list["Citation"]] = relationship(
        back_populates="target_post", foreign_keys="Citation.target_post_id"
    )
    votes: Mapped[list["Vote"]] = relationship(back_populates="post")  # noqa: F821
    claims: Mapped[list["Claim"]] = relationship(back_populates="post")  # noqa: F821
    tags: Mapped[list["PostTag"]] = relationship(back_populates="post")  # noqa: F821

    __table_args__ = (
        Index("ix_posts_thread_sequence", "thread_id", "sequence_in_thread"),
    )


class Citation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "citations"

    source_post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_post: Mapped["Post"] = relationship(
        back_populates="citations_made", foreign_keys=[source_post_id]
    )
    target_post: Mapped["Post"] = relationship(
        back_populates="citations_received", foreign_keys=[target_post_id]
    )

    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('supports', 'opposes', 'extends', 'corrects')",
            name="ck_citations_relationship_type",
        ),
    )
