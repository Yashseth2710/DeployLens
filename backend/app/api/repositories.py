from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, GitHubToken
from app.models.repository import Repository
from app.schemas.deployment import SyncSummary
from app.schemas.repository import (
    AvailableRepository,
    ConnectedRepository,
    ConnectRepositoryRequest,
)
from app.services import github_api, workflow_sync
from app.services.workflow_sync import SyncResult

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.get("", response_model=list[ConnectedRepository])
def list_connected(user: CurrentUser, db: DbSession) -> list[Repository]:
    return list(
        db.scalars(
            select(Repository)
            .where(Repository.user_id == user.id)
            # connected_at comes from now(), which is fixed per transaction; the
            # uuidv7 primary key breaks the tie in the same direction.
            .order_by(Repository.connected_at.desc(), Repository.id.desc())
        )
    )


@router.get("/available", response_model=list[AvailableRepository])
def list_available(user: CurrentUser, db: DbSession, token: GitHubToken) -> list[dict[str, object]]:
    """The picker needs every repository the token can see, with the ones already being
    tracked marked so they render as connected rather than as a duplicate offer."""
    connected = set(
        db.scalars(select(Repository.github_repo_id).where(Repository.user_id == user.id))
    )
    return [
        {**asdict(repository), "connected": repository.github_repo_id in connected}
        for repository in github_api.list_repositories(token)
    ]


@router.post("", response_model=ConnectedRepository, status_code=status.HTTP_201_CREATED)
def connect(
    payload: ConnectRepositoryRequest, user: CurrentUser, db: DbSession, token: GitHubToken
) -> Repository:
    if _owned(db, user.id, github_repo_id=payload.github_repo_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That repository is already connected")

    # Read back from GitHub rather than trusting the name the client sent: a repository
    # the token cannot see answers 404, which is exactly the rejection we want.
    details = github_api.get_repository(token, payload.github_repo_id)

    repository = Repository(
        user_id=user.id,
        github_repo_id=details.github_repo_id,
        name=details.name,
        full_name=details.full_name,
        owner=details.owner,
        default_branch=details.default_branch,
        github_url=details.github_url,
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)
    return repository


@router.post("/{repository_id}/sync", response_model=SyncSummary)
def sync(repository_id: UUID, user: CurrentUser, db: DbSession, token: GitHubToken) -> SyncResult:
    """Pulls Actions runs for one repository. Safe to call repeatedly - runs are keyed
    on their GitHub id, so a second pass updates rather than duplicates."""
    repository = _owned(db, user.id, repository_id=repository_id)
    if repository is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connected repository")

    return workflow_sync.sync_repository(db, repository, token)


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(repository_id: UUID, user: CurrentUser, db: DbSession) -> None:
    """Cascades to the runs, deployments and health checks collected for it — a
    disconnected repository leaves nothing behind to reconnect into."""
    repository = _owned(db, user.id, repository_id=repository_id)
    if repository is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connected repository")

    db.delete(repository)
    db.commit()


def _owned(
    db: DbSession,
    user_id: UUID,
    *,
    repository_id: UUID | None = None,
    github_repo_id: int | None = None,
) -> Repository | None:
    query = select(Repository).where(Repository.user_id == user_id)
    if repository_id is not None:
        query = query.where(Repository.id == repository_id)
    if github_repo_id is not None:
        query = query.where(Repository.github_repo_id == github_repo_id)
    return db.scalar(query)
