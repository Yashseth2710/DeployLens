from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.repository import Repository
from app.models.workflow import WorkflowRun
from app.schemas.analytics import (
    AttentionOut,
    InsightsOut,
    OverviewOut,
    RepositoryDetailOut,
    TrendOut,
)
from app.services import insights, metrics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# A finished project has no activity this month; reading its whole life is the
# point of connecting it, so the ceiling is a year rather than a quarter.
WindowDays = Annotated[int, Query(ge=1, le=365)]

# The dashboard band names what is worst, not everything that is wrong. Two lines a
# project keeps it a summary that points somewhere rather than a second report.
ATTENTION_PER_REPOSITORY = 2


@router.get("/overview", response_model=OverviewOut)
def overview(user: CurrentUser, db: DbSession, days: WindowDays = 30) -> dict[str, Any]:
    """Totals across every connected repository, plus the per-repository breakdown the
    dashboard cards read. One request, because the dashboard is one screen."""
    repository_ids = _owned_ids(db, user.id)
    delivery = metrics.delivery_metrics(db, repository_ids, days)
    uptime = metrics.uptime_metrics(db, repository_ids, days)
    pipeline = metrics.pipeline_metrics(db, repository_ids, days)

    return {
        "window_days": days,
        "connected_repositories": len(repository_ids),
        "delivery": delivery,
        "pipeline": pipeline,
        "uptime": uptime,
        "review": metrics.review_metrics(db, repository_ids, days),
        "health_score": metrics.health_score(delivery, uptime, pipeline),
        "repositories": metrics.per_repository(db, user.id, days),
    }


@router.get("/repositories/{repository_id}", response_model=RepositoryDetailOut)
def repository_detail(
    repository_id: UUID, user: CurrentUser, db: DbSession, days: WindowDays = 30
) -> dict[str, Any]:
    """One repository read on its own. The dashboard answers "how is everything", which
    is a different question from "what is going on with this project" — the breakdowns
    by workflow and by branch only mean anything once a single repository is in scope."""
    repository = db.scalar(
        select(Repository).where(Repository.id == repository_id, Repository.user_id == user.id)
    )
    if repository is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connected repository")

    ids = [repository_id]
    delivery = metrics.delivery_metrics(db, ids, days)
    uptime = metrics.uptime_metrics(db, ids, days)
    pipeline = metrics.pipeline_metrics(db, ids, days)

    return {
        "repository": repository,
        "window_days": days,
        "delivery": delivery,
        "pipeline": pipeline,
        "uptime": uptime,
        "review": metrics.review_metrics(db, ids, days),
        "health_score": metrics.health_score(delivery, uptime, pipeline),
        "workflows": metrics.run_groups(db, repository_id, days, WorkflowRun.workflow_name),
        "branches": metrics.run_groups(db, repository_id, days, WorkflowRun.branch),
        "first_activity_at": metrics.first_activity_at(db, repository_id),
    }


@router.get("/trends", response_model=TrendOut)
def trends(
    user: CurrentUser,
    db: DbSession,
    repository_id: UUID | None = None,
    days: WindowDays = 30,
) -> dict[str, Any]:
    repository_ids = _owned_ids(db, user.id)
    if repository_id is not None:
        if repository_id not in repository_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connected repository")
        repository_ids = [repository_id]

    return {
        "window_days": days,
        "runs": metrics.run_series(db, repository_ids, days),
        "deployments": metrics.deployment_series(db, repository_ids, days),
        "uptime": metrics.uptime_series(db, repository_ids, days),
    }


@router.get("/repositories/{repository_id}/insights", response_model=InsightsOut)
def repository_insights(
    repository_id: UUID, user: CurrentUser, db: DbSession, days: WindowDays = 30
) -> dict[str, Any]:
    """What is going wrong in one project, and why it counts as wrong.

    Kept off the detail response rather than folded into it: the breakdowns there are
    counts, and this reads every run in the window to compare them against each other.
    A page that wants the numbers should not pay for the reasoning.
    """
    owned = db.scalar(
        select(Repository.id).where(Repository.id == repository_id, Repository.user_id == user.id)
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connected repository")

    return {"window_days": days, "findings": insights.findings_for(db, repository_id, days)}


@router.get("/attention", response_model=AttentionOut)
def attention(user: CurrentUser, db: DbSession, days: WindowDays = 30) -> dict[str, Any]:
    """The same reading across every project, so the dashboard can say which one needs
    looking at. Projects with nothing wrong are left out entirely — an empty list is
    the good answer, and padding it with reassurance would bury the real rows."""
    return {
        "window_days": days,
        "repositories": insights.across_repositories(db, user.id, days, ATTENTION_PER_REPOSITORY),
    }


def _owned_ids(db: DbSession, user_id: UUID) -> list[UUID]:
    return list(db.scalars(select(Repository.id).where(Repository.user_id == user_id)))
