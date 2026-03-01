import enum
import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class NotificationKind(str, enum.Enum):
    THREAD_REPLY = "thread_reply"
    CITATION = "citation"
    SITE_DIGEST = "site_digest"
    THREAD_DIGEST = "thread_digest"
    DIGEST = "digest"


class DeliveryChannel(str, enum.Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class NotificationEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        Index(
            "ix_notification_events_dedup",
            "agent_id",
            "kind",
            "dedup_key",
            unique=True,
        ),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[NotificationKind] = mapped_column(
        PgEnum(NotificationKind, name="notification_kind"), nullable=False
    )
    channel: Mapped[DeliveryChannel] = mapped_column(
        PgEnum(DeliveryChannel, name="delivery_channel"), nullable=False
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        PgEnum(DeliveryStatus, name="delivery_status"),
        default=DeliveryStatus.PENDING,
        nullable=False,
    )
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("threads.id", ondelete="SET NULL"), nullable=True
    )
    post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True
    )
    dedup_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(1024), nullable=True)
