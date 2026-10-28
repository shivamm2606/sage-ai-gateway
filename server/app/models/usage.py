from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageRecord(Base):
    """One row per chat request: tokens, latency and how the model was chosen."""

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL so deleting a chat doesn't wipe usage and reset someone's quota
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )

    requested_model: Mapped[str] = mapped_column(String(100), nullable=False)  # may be "auto"
    model: Mapped[str] = mapped_column(String(100), nullable=False)  # what actually answered
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # true when the provider didn't report usage and we counted roughly ourselves
    tokens_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    first_token_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    routing_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    routing_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    routing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
