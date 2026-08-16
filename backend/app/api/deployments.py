from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.repository import Repository
from app.models.workflow import Deployment
from app.schemas.deployment import DeploymentDetail, DeploymentSummary

router = APIRouter(prefix="/api/deployments", tags=["deployments"])


@router.get("", response_model=list[DeploymentSummary])
def list_deployments(
    user: CurrentUser,
    db: DbSession,
    repository_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    """Across every connected repository unless one is named, newest first — the shape
    both the dashboard's activity feed and the history page read from."""
    query = (
        select(Deployment, Repository.full_name)
        .join(Repository, Deployment.repository_id == Repository.id)
        .where(Repository.user_id == user.id)
        .order_by(Deployment.started_at.desc().nullslast(), Deployment.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if repository_id is not None:
        query = query.where(Deployment.repository_id == repository_id)

    return [_summary(deployment, full_name) for deployment, full_name in db.execute(query)]


@router.get("/{deployment_id}", response_model=DeploymentDetail)
def get_deployment(deployment_id: UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    row = db.execute(
        select(Deployment, Repository.full_name)
        .join(Repository, Deployment.repository_id == Repository.id)
        .where(Repository.user_id == user.id, Deployment.id == deployment_id)
        .options(selectinload(Deployment.workflow_run))
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such deployment")

    deployment, full_name = row
    return {**_summary(deployment, full_name), "workflow_run": deployment.workflow_run}


def _summary(deployment: Deployment, repository_full_name: str) -> dict[str, Any]:
    return {
        "id": deployment.id,
        "repository_id": deployment.repository_id,
        "repository_full_name": repository_full_name,
        "environment": deployment.environment,
        "status": deployment.status,
        "branch": deployment.branch,
        "commit_sha": deployment.commit_sha,
        "author": deployment.author,
        "started_at": deployment.started_at,
        "completed_at": deployment.completed_at,
        "duration_seconds": deployment.duration_seconds,
    }
