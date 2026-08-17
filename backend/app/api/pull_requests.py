from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.history import PullRequest
from app.models.repository import Repository
from app.schemas.history import PullRequestRow

router = APIRouter(prefix="/api/pull-requests", tags=["pull requests"])

STATES = ("open", "merged", "abandoned")


@router.get("", response_model=list[PullRequestRow])
def list_pull_requests(
    user: CurrentUser,
    db: DbSession,
    repository_id: UUID | None = None,
    state: Annotated[str | None, Query(pattern="^(open|merged|abandoned)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    """Newest first by when each was opened.

    `state` is ours rather than GitHub's: GitHub calls a merged and an abandoned pull
    request both "closed", and the difference between them is the only reason to look
    at this list.
    """
    query = (
        select(PullRequest, Repository.full_name)
        .join(Repository, PullRequest.repository_id == Repository.id)
        .where(Repository.user_id == user.id)
        .order_by(PullRequest.opened_at.desc().nullslast(), PullRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if repository_id is not None:
        query = query.where(PullRequest.repository_id == repository_id)
    if state == "open":
        query = query.where(PullRequest.state == "open")
    elif state == "merged":
        query = query.where(PullRequest.merged_at.is_not(None))
    elif state == "abandoned":
        query = query.where(PullRequest.state == "closed", PullRequest.merged_at.is_(None))

    return [
        {
            "id": pull_request.id,
            "repository_id": pull_request.repository_id,
            "repository_full_name": full_name,
            "number": pull_request.number,
            "title": pull_request.title,
            "author": pull_request.author,
            "outcome": outcome_of(pull_request),
            "draft": pull_request.draft,
            "head_branch": pull_request.head_branch,
            "base_branch": pull_request.base_branch,
            "html_url": pull_request.html_url,
            "opened_at": pull_request.opened_at,
            "merged_at": pull_request.merged_at,
            "closed_at": pull_request.closed_at,
        }
        for pull_request, full_name in db.execute(query)
    ]


def outcome_of(pull_request: PullRequest) -> str:
    if pull_request.merged_at is not None:
        return "merged"
    if pull_request.state == "closed":
        return "abandoned"
    return "open"
