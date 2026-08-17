from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.repository import Repository
from app.models.workflow import WorkflowRun
from app.schemas.analytics import OverviewOut, RepositoryDetailOut, TrendOut
from app.services import metrics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# A finished project has no activity this month; reading its whole life is the
# point of connecting it, so the ceiling is a year rather than a quarter.
WindowDays = Annotated[int, Query(ge=1, le=365)]


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
        "deployments": metrics.deployment_series(db, repository_ids, days),
        "uptime": metrics.uptime_series(db, repository_ids, days),
    }


def _owned_ids(db: DbSession, user_id: UUID) -> list[UUID]:
    return list(db.scalars(select(Repository.id).where(Repository.user_id == user_id)))
