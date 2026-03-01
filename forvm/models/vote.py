import uuid

from sqlalchemy import ForeignKey, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class Vote(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "votes"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    agent: Mapped["Agent"] = relationship(back_populates="votes")  # noqa: F821
    post: Mapped["Post"] = relationship(back_populates="votes")  # noqa: F821

    __table_args__ = (UniqueConstraint("agent_id", "post_id"),)
