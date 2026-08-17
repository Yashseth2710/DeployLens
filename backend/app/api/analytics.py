from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.repository import Repository
from app.schemas.analytics import OverviewOut, TrendOut
from app.services import metrics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

WindowDays = Annotated[int, Query(ge=1, le=90)]


@router.get("/overview", response_model=OverviewOut)
def overview(user: CurrentUser, db: DbSession, days: WindowDays = 30) -> dict[str, Any]:
    """Totals across every connected repository, plus the per-repository breakdown the
    dashboard cards read. One request, because the dashboard is one screen."""
    repository_ids = _owned_ids(db, user.id)
    delivery = metrics.delivery_metrics(db, repository_ids, days)
    uptime = metrics.uptime_metrics(db, repository_ids, days)

    return {
        "window_days": days,
        "connected_repositories": len(repository_ids),
        "delivery": delivery,
        "uptime": uptime,
        "health_score": metrics.health_score(delivery, uptime),
        "repositories": metrics.per_repository(db, user.id, days),
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
