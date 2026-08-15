from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, PrimaryKeyMixin, TimestampMixin


class WebhookEvent(Base, PrimaryKeyMixin, TimestampMixin):
    """Every delivery GitHub sends, stored before it is interpreted.

    Two reasons this table exists. The unique delivery id makes reprocessing a
    redelivered event a no-op, and keeping the raw payload means a parsing bug can be
    diagnosed and replayed rather than guessed at from a log line.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (
        # Partial index: the retry sweep only ever looks for unprocessed rows, which
        # stay a tiny fraction of the table.
        Index(
            "ix_webhook_events_unprocessed",
            "created_at",
            postgresql_where=text("processed = false"),
        ),
    )

    # GitHub's X-GitHub-Delivery header. Unique, so a redelivery collides instead of
    # double-counting a deployment.
    github_delivery_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Nullable and intentionally not cascading: an event from a repository the user has
    # since disconnected is still worth keeping for diagnosis.
    repository_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL")
    )

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
