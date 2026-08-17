from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.health import HealthCheck
    from app.models.user import User
    from app.models.workflow import Deployment, WorkflowRun


class Repository(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "repositories"
    __table_args__ = (
        # The same GitHub repository can be connected by two different users, but
        # never twice by one.
        UniqueConstraint("user_id", "github_repo_id", name="uq_repositories_user_repo"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    github_repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    full_name: Mapped[str] = mapped_column(String(140), nullable=False)
    owner: Mapped[str] = mapped_column(String(39), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    github_url: Mapped[str] = mapped_column(Text, nullable=False)

    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # When GitHub was last read for this repository. Null means never, which is what
    # makes a freshly connected repository the first thing the next sweep collects.
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="repositories")
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    health_checks: Mapped[list["HealthCheck"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
