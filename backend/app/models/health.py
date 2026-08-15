from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.repository import Repository


class HealthCheck(Base, PrimaryKeyMixin, TimestampMixin):
    """A URL to probe on a schedule."""

    __tablename__ = "health_checks"

    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    # Hourly by default: each probe wakes the database and holds it awake through
    # Neon's idle window, so cadence drives compute spend far more than query cost.
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    expected_status: Mapped[int] = mapped_column(Integer, nullable=False, server_default="200")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    repository: Mapped["Repository"] = relationship(back_populates="health_checks")
    results: Mapped[list["HealthResult"]] = relationship(
        back_populates="health_check", cascade="all, delete-orphan"
    )


class HealthResult(Base, PrimaryKeyMixin):
    """One probe outcome. The highest-volume table in the schema, and the one the
    retention policy trims."""

    __tablename__ = "health_results"
    __table_args__ = (
        CheckConstraint("status IN ('up', 'down')", name="ck_health_results_status"),
        # Serves both the history charts and the retention sweep.
        Index("ix_health_results_check_checked", "health_check_id", text("checked_at DESC")),
    )

    health_check_id: Mapped[UUID] = mapped_column(
        ForeignKey("health_checks.id", ondelete="CASCADE"), nullable=False
    )

    # Ours to control, unlike the GitHub-sourced statuses, so a constraint is safe here.
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    health_check: Mapped["HealthCheck"] = relationship(back_populates="results")
