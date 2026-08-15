from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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


class WorkflowRun(Base, PrimaryKeyMixin, TimestampMixin):
    """A single GitHub Actions run. Status and conclusion are stored as free text
    rather than enums because GitHub adds values to both over time, and a webhook
    carrying an unrecognised one should still persist."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        # Makes webhook processing idempotent: a redelivered event upserts the same row.
        UniqueConstraint("repository_id", "github_run_id", name="uq_workflow_runs_repo_run"),
        # Every dashboard query reads a repository's runs newest-first.
        Index("ix_workflow_runs_repo_started", "repository_id", text("started_at DESC")),
    )

    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    github_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255))
    commit_sha: Mapped[str | None] = mapped_column(String(40))

    status: Mapped[str] = mapped_column(String(30), nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(30))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Denormalised from the timestamps so duration averages do not recompute per row.
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    html_url: Mapped[str | None] = mapped_column(Text)

    repository: Mapped["Repository"] = relationship(back_populates="workflow_runs")
    deployment: Mapped["Deployment | None"] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan"
    )


class Deployment(Base, PrimaryKeyMixin, TimestampMixin):
    """A workflow run that shipped something. Kept separate from WorkflowRun because
    most runs are tests or lint that never deploy, and reliability metrics should not
    count them."""

    __tablename__ = "deployments"
    __table_args__ = (
        Index("ix_deployments_repo_started", "repository_id", text("started_at DESC")),
    )

    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True
    )

    environment: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="production"
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)

    branch: Mapped[str | None] = mapped_column(String(255))
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    author: Mapped[str | None] = mapped_column(String(255))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    deployment_url: Mapped[str | None] = mapped_column(Text)

    repository: Mapped["Repository"] = relationship(back_populates="deployments")
    workflow_run: Mapped["WorkflowRun | None"] = relationship(back_populates="deployment")
