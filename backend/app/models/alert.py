from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.repository import Repository


class Alert(Base, PrimaryKeyMixin, TimestampMixin):
    """One raised problem, and what was done about it.

    A sweep runs repeatedly over the same window, so the same broken workflow is
    detected again on every pass. Without a record of what has already been said,
    each pass would open another issue about the same failure. This row is that
    record: the subject it is about, the issue it opened, and whether the problem
    is still standing.

    `subject` and `kind` together are the identity of a problem — "CI is on a
    failing streak" is the same problem this hour as it was last hour, even
    though the run count behind it has moved.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        # One *open* alert per subject per repository, enforced where it matters.
        # The kind is deliberately not part of this: a workflow failing repeatedly is
        # both a streak and a chronic failure, and keying on both would let the same
        # broken workflow hold two open issues at once.
        #
        # A plain unique constraint cannot express "open" — Postgres treats NULLs as
        # distinct, so every unresolved row would satisfy it. Resolved rows stay on
        # the table, so the same problem returning later reads as a recurrence.
        Index(
            "uq_alert_open",
            "repository_id",
            "subject",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)

    # Null until the issue is actually filed, which is the whole state a dry run
    # leaves behind: the alert was decided, nothing was written to GitHub.
    issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set when the pipeline recovers. A resolved alert stays on the table so the
    # same problem returning later reads as a recurrence rather than as noise.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped["Repository"] = relationship(back_populates="alerts")
