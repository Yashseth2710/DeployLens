from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.repository import Repository
from app.models.workflow import WorkflowRun
from app.schemas.deployment import WorkflowRunRow

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[WorkflowRunRow])
def list_runs(
    user: CurrentUser,
    db: DbSession,
    repository_id: UUID | None = None,
    branch: str | None = None,
    event: str | None = None,
    conclusion: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    """Every Actions run, not only the ones that shipped. A failing test on a pull
    request is delivery information too, and it is the question a developer asks most
    often — this endpoint is what the activity feed and the filters read."""
    query = (
        select(WorkflowRun, Repository.full_name)
        .join(Repository, WorkflowRun.repository_id == Repository.id)
        .where(Repository.user_id == user.id)
        .order_by(WorkflowRun.started_at.desc().nullslast(), WorkflowRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if repository_id is not None:
        query = query.where(WorkflowRun.repository_id == repository_id)
    if branch is not None:
        query = query.where(WorkflowRun.branch == branch)
    if event is not None:
        query = query.where(WorkflowRun.event == event)
    if conclusion is not None:
        query = query.where(WorkflowRun.conclusion == conclusion)

    return [
        {
            "id": run.id,
            "repository_id": run.repository_id,
            "repository_full_name": full_name,
            "github_run_id": run.github_run_id,
            "workflow_name": run.workflow_name,
            "branch": run.branch,
            "commit_sha": run.commit_sha,
            "status": run.status,
            "conclusion": run.conclusion,
            "event": run.event,
            "actor": run.actor,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "duration_seconds": run.duration_seconds,
            "html_url": run.html_url,
        }
        for run, full_name in db.execute(query)
    ]
