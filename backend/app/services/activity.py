from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.repository import Repository
from app.models.workflow import Deployment, WorkflowRun

# GitHub reports a run's progress in `status` and only fills `conclusion` once it is
# over, so "not completed" is the honest test for in flight. Values are matched rather
# than enumerated exhaustively: GitHub adds to this list, and an unrecognised status on
# a run with no conclusion is still something that has not finished.
SETTLED_RUN_STATUSES = ("completed",)
IN_FLIGHT_DEPLOY_STATUSES = ("pending", "queued", "in_progress", "waiting", "created")

# A finished item stays on the board briefly so the moment it lands is visible. Without
# it, a run that passes vanishes from the page and the answer looks like it never ran.
SETTLED_GRACE_MINUTES = 15

# GitHub cancels a job at six hours, so a run still recorded as in flight beyond that is
# not running — it is a row nothing has been able to correct, which is what happens while
# a token is expired. Counting a timer up past that point states something false with
# increasing confidence, so those rows are left off the board entirely. A sync repairs
# them the moment access is restored, because the upsert carries the real conclusion.
ABANDONED_AFTER_HOURS = 6


@dataclass(frozen=True)
class ActivityItem:
    kind: str
    id: UUID
    repository_id: UUID
    repository_full_name: str
    title: str
    detail: str | None
    status: str
    conclusion: str | None
    live: bool
    started_at: datetime | None
    completed_at: datetime | None
    url: str | None


def board(db: Session, user_id: UUID) -> list[ActivityItem]:
    """Everything in flight, plus whatever settled in the last few minutes. The two are
    returned together and separated by the `live` flag, so the page can watch an item
    change state in place rather than having it disappear and a different one appear."""
    items = _runs(db, user_id) + _deployments(db, user_id)
    # Live first, then newest within each group. A running item is the thing being
    # watched; the settled ones underneath it are the record of what just happened.
    items.sort(key=lambda item: (item.live, _started(item)), reverse=True)
    return items


def _within(started_at: datetime | None) -> bool:
    """Read in Python as well as in SQL, so the flag the page renders and the rows the
    query returns cannot disagree about what counts as still running."""
    if started_at is None:
        return False
    return datetime.now(UTC) - started_at < timedelta(hours=ABANDONED_AFTER_HOURS)


def _started(item: "ActivityItem") -> float:
    return item.started_at.timestamp() if item.started_at else 0.0


def _runs(db: Session, user_id: UUID) -> list[ActivityItem]:
    live = WorkflowRun.status.not_in(SETTLED_RUN_STATUSES) & (
        WorkflowRun.started_at >= _abandoned_cutoff()
    )
    rows = db.execute(
        select(WorkflowRun, Repository.full_name)
        .join(Repository, WorkflowRun.repository_id == Repository.id)
        .where(
            Repository.user_id == user_id,
            live | (WorkflowRun.completed_at >= _grace_cutoff()),
        )
        .order_by(WorkflowRun.started_at.desc().nullslast())
        .limit(40)
    ).all()

    return [
        ActivityItem(
            kind="run",
            id=run.id,
            repository_id=run.repository_id,
            repository_full_name=full_name,
            title=run.workflow_name,
            detail=run.branch,
            status=run.status,
            conclusion=run.conclusion,
            live=run.status not in SETTLED_RUN_STATUSES and _within(run.started_at),
            started_at=run.started_at,
            completed_at=run.completed_at,
            url=run.html_url,
        )
        for run, full_name in rows
    ]


def _deployments(db: Session, user_id: UUID) -> list[ActivityItem]:
    live = Deployment.status.in_(IN_FLIGHT_DEPLOY_STATUSES) & (
        Deployment.started_at >= _abandoned_cutoff()
    )
    rows = db.execute(
        select(Deployment, Repository.full_name)
        .join(Repository, Deployment.repository_id == Repository.id)
        .where(
            Repository.user_id == user_id,
            live | (Deployment.completed_at >= _grace_cutoff()),
        )
        .order_by(Deployment.started_at.desc().nullslast())
        .limit(20)
    ).all()

    return [
        ActivityItem(
            kind="deploy",
            id=deployment.id,
            repository_id=deployment.repository_id,
            repository_full_name=full_name,
            title=f"Deploy to {deployment.environment}",
            detail=deployment.branch,
            status=deployment.status,
            conclusion=None
            if deployment.status in IN_FLIGHT_DEPLOY_STATUSES
            else deployment.status,
            live=deployment.status in IN_FLIGHT_DEPLOY_STATUSES and _within(deployment.started_at),
            started_at=deployment.started_at,
            completed_at=deployment.completed_at,
            url=deployment.deployment_url,
        )
        for deployment, full_name in rows
    ]


def _grace_cutoff() -> ColumnElement[Any]:
    return func.now() - func.make_interval(0, 0, 0, 0, 0, SETTLED_GRACE_MINUTES)


def _abandoned_cutoff() -> ColumnElement[Any]:
    return func.now() - func.make_interval(0, 0, 0, 0, ABANDONED_AFTER_HOURS)
