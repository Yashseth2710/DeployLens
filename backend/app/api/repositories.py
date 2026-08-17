from contextlib import suppress
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
from app.services import github_api, webhooks, workflow_sync
from app.services.github_api import GitHubError
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
    connected = {
        github_repo_id: repository_id
        for github_repo_id, repository_id in db.execute(
            select(Repository.github_repo_id, Repository.id).where(Repository.user_id == user.id)
        ).all()
    }
    return [
        {
            **asdict(repository),
            "connected": repository.github_repo_id in connected,
            "connected_id": connected.get(repository.github_repo_id),
        }
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

    _ensure_webhook(token, repository)
    return repository


@router.post("/{repository_id}/sync", response_model=SyncSummary)
def sync(repository_id: UUID, user: CurrentUser, db: DbSession, token: GitHubToken) -> SyncResult:
    """Pulls Actions runs for one repository. Safe to call repeatedly - runs are keyed
    on their GitHub id, so a second pass updates rather than duplicates."""
    repository = _owned(db, user.id, repository_id=repository_id)
    if repository is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connected repository")

    result = workflow_sync.sync_repository(db, repository, token)
    _ensure_webhook(token, repository)
    return result


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(repository_id: UUID, user: CurrentUser, db: DbSession, token: GitHubToken) -> None:
    """Cascades to the runs, deployments and health checks collected for it — a
    disconnected repository leaves nothing behind to reconnect into."""
    repository = _owned(db, user.id, repository_id=repository_id)
    if repository is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connected repository")

    if not _connected_elsewhere(db, repository):
        # Disconnecting is a local decision. A hook left behind because GitHub was
        # unreachable only costs deliveries that no longer match a repository.
        with suppress(GitHubError):
            webhooks.unregister(token, repository)

    db.delete(repository)
    db.commit()


def _ensure_webhook(token: str, repository: Repository) -> None:
    """A repository is connected whether or not the hook could be created, because the
    history is still reachable by syncing. Every later sync retries the registration,
    so a GitHub outage during connect costs live updates until the next refresh rather
    than leaving the repository permanently unhooked."""
    with suppress(GitHubError):
        webhooks.register(token, repository)


def _connected_elsewhere(db: DbSession, repository: Repository) -> bool:
    """Two accounts can track the same repository through one hook, so the hook only
    goes when the last of them disconnects."""
    other = db.scalar(
        select(Repository.id).where(
            Repository.github_repo_id == repository.github_repo_id,
            Repository.id != repository.id,
        )
    )
    return other is not None


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
