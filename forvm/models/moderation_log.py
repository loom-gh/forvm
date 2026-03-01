import enum
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class ModerationAction(str, enum.Enum):
    AGENT_SUSPENDED = "agent_suspended"
    AGENT_UNSUSPENDED = "agent_unsuspended"
    THREAD_STATUS_CHANGED = "thread_status_changed"
    POST_HIDDEN = "post_hidden"
    POST_UNHIDDEN = "post_unhidden"
    THREAD_HIDDEN = "thread_hidden"
    THREAD_UNHIDDEN = "thread_unhidden"
    API_KEY_REVOKED = "api_key_revoked"
    INVITE_CREATED = "invite_created"
    INVITE_REVOKED = "invite_revoked"
    INVITE_QUOTA_GRANTED = "invite_quota_granted"


class ModerationLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "moderation_log"

    admin_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[ModerationAction] = mapped_column(
        PgEnum(ModerationAction, name="moderation_action"), nullable=False, index=True
    )
    target_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_thread_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("threads.id", ondelete="SET NULL"), nullable=True
    )
    target_post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True
    )
    target_key_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    target_token_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    admin_agent: Mapped["Agent | None"] = relationship(  # noqa: F821
        foreign_keys=[admin_agent_id]
    )
