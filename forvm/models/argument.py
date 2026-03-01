import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forvm.database import Base
from forvm.models.mixins import TimestampMixin, UUIDMixin


class Claim(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "claims"

    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(32), nullable=False)
    supports_post_ids: Mapped[list] = mapped_column(JSONB, default=list)
    opposes_post_ids: Mapped[list] = mapped_column(JSONB, default=list)
    novelty_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    post: Mapped["Post"] = relationship(back_populates="claims")  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            "claim_type IN ('assertion', 'evidence', 'rebuttal', 'concession')",
            name="ck_claims_claim_type",
        ),
    )
