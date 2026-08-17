from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.repository import Repository


class PullRequest(Base, PrimaryKeyMixin, TimestampMixin):
    """A pull request, kept because "was it merged or abandoned" is the difference
    between work that shipped and work that did not, and no other table records it.

    State is stored as GitHub sends it rather than as an enum: a closed pull request
    with a `merged_at` was merged, and one without it was dropped. GitHub reports both
    as "closed", so the timestamp is the fact and the word is not.
    """

    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repository_id", "number", name="uq_pull_requests_repo_number"),
        Index("ix_pull_requests_repo_opened", "repository_id", text("opened_at DESC")),
    )

    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    draft: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    head_branch: Mapped[str | None] = mapped_column(String(255))
    base_branch: Mapped[str | None] = mapped_column(String(255))
    html_url: Mapped[str | None] = mapped_column(Text)

    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repository: Mapped["Repository"] = relationship(back_populates="pull_requests")


class CommitWeek(Base, PrimaryKeyMixin, TimestampMixin):
    """A week's commit total. Deliberately not a row per commit.

    Every question this product asks about commits is about volume and rhythm — is the
    project active, is it speeding up, when did it start. A row per commit would be
    orders of magnitude more storage to answer none of them better, and the free tier
    is the constraint the whole design is built around.
    """

    __tablename__ = "commit_weeks"
    __table_args__ = (
        UniqueConstraint("repository_id", "week_start", name="uq_commit_weeks_repo_week"),
    )

    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    commits: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    repository: Mapped["Repository"] = relationship(back_populates="commit_weeks")
