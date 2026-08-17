from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.history import CommitWeek, PullRequest
from app.models.repository import Repository
from app.services import github_api
from app.services.github_api import GitHubCommitWeek, GitHubPullRequest

# A first collection reaches back for a project's whole life; after that only the most
# recently updated page can hold anything unseen, because GitHub sorts by update time.
FIRST_SYNC_PAGES = 5
REFRESH_PAGES = 1


@dataclass(frozen=True)
class HistoryResult:
    pull_requests_seen: int
    commit_weeks: int


@dataclass(frozen=True)
class HistoryPayload:
    pull_requests: list[GitHubPullRequest]
    commit_weeks: list[GitHubCommitWeek]


def plan(db: Session, repository: Repository) -> int:
    known = db.scalar(
        select(PullRequest.id).where(PullRequest.repository_id == repository.id).limit(1)
    )
    return REFRESH_PAGES if known else FIRST_SYNC_PAGES


def fetch(access_token: str, full_name: str, pages: int, with_commits: bool) -> HistoryPayload:
    """Pull requests every pass, commit totals only when asked for.

    They answer at different speeds: a merge has to appear promptly or the board is
    simply wrong, while a year of weekly commit counts is the same year it was a
    minute ago.
    """
    return HistoryPayload(
        pull_requests=github_api.list_pull_requests(access_token, full_name, pages=pages),
        commit_weeks=github_api.commit_activity(access_token, full_name) if with_commits else [],
    )


def record(db: Session, repository: Repository, payload: HistoryPayload) -> HistoryResult:
    record_pull_requests(db, repository, payload.pull_requests)
    if payload.commit_weeks:
        record_commit_weeks(db, repository, payload.commit_weeks)
    db.commit()
    return HistoryResult(
        pull_requests_seen=len(payload.pull_requests), commit_weeks=len(payload.commit_weeks)
    )


def record_pull_requests(
    db: Session, repository: Repository, pull_requests: list[GitHubPullRequest]
) -> None:
    """Keyed on the repository and the pull request number, so a resync updates the
    state of one that has since been merged rather than storing it twice.

    Written as one statement: a hundred pull requests inserted one at a time is a
    hundred round trips to a database that is seventy milliseconds away.
    """
    if not pull_requests:
        return

    unique = {pull_request.number: pull_request for pull_request in pull_requests}
    statement = insert(PullRequest).values(
        [_pull_request_values(repository, pull_request) for pull_request in unique.values()]
    )
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_pull_requests_repo_number",
            set_={
                key: getattr(statement.excluded, key)
                for key in ("title", "state", "draft", "updated_at", "merged_at", "closed_at")
            },
        )
    )


def _pull_request_values(
    repository: Repository, pull_request: GitHubPullRequest
) -> dict[str, object]:
    return {
        "repository_id": repository.id,
        "number": pull_request.number,
        "title": pull_request.title[:500],
        "author": pull_request.author,
        "state": pull_request.state,
        "draft": pull_request.draft,
        "head_branch": pull_request.head_branch,
        "base_branch": pull_request.base_branch,
        "html_url": pull_request.html_url,
        "opened_at": pull_request.opened_at,
        "updated_at": pull_request.updated_at,
        "merged_at": pull_request.merged_at,
        "closed_at": pull_request.closed_at,
    }


def record_commit_weeks(db: Session, repository: Repository, weeks: list[GitHubCommitWeek]) -> None:
    """A week that is still in progress gains commits after we first see it, so every
    week is overwritten on each pass rather than inserted once — a year of weeks in one
    statement rather than fifty two."""
    if not weeks:
        return

    unique = {week.week_start: week for week in weeks}
    statement = insert(CommitWeek).values(
        [
            {
                "repository_id": repository.id,
                "week_start": week.week_start,
                "commits": week.commits,
            }
            for week in unique.values()
        ]
    )
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_commit_weeks_repo_week",
            set_={"commits": statement.excluded.commits},
        )
    )
