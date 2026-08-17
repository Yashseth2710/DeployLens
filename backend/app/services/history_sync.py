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


def sync_history(db: Session, repository: Repository, access_token: str) -> HistoryResult:
    known = db.scalar(
        select(PullRequest.id).where(PullRequest.repository_id == repository.id).limit(1)
    )
    pages = REFRESH_PAGES if known else FIRST_SYNC_PAGES

    pull_requests = github_api.list_pull_requests(access_token, repository.full_name, pages=pages)
    record_pull_requests(db, repository, pull_requests)

    weeks = github_api.commit_activity(access_token, repository.full_name)
    record_commit_weeks(db, repository, weeks)

    db.commit()
    return HistoryResult(pull_requests_seen=len(pull_requests), commit_weeks=len(weeks))


def record_pull_requests(
    db: Session, repository: Repository, pull_requests: list[GitHubPullRequest]
) -> None:
    """Keyed on the repository and the pull request number, so a resync updates the
    state of one that has since been merged rather than storing it twice."""
    for pull_request in pull_requests:
        values = {
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
        db.execute(
            insert(PullRequest)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_pull_requests_repo_number",
                set_={
                    key: values[key]
                    for key in (
                        "title",
                        "state",
                        "draft",
                        "updated_at",
                        "merged_at",
                        "closed_at",
                    )
                },
            )
        )


def record_commit_weeks(db: Session, repository: Repository, weeks: list[GitHubCommitWeek]) -> None:
    """A week that is still in progress gains commits after we first see it, so every
    week is overwritten on each pass rather than inserted once."""
    for week in weeks:
        values = {
            "repository_id": repository.id,
            "week_start": week.week_start,
            "commits": week.commits,
        }
        db.execute(
            insert(CommitWeek)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_commit_weeks_repo_week", set_={"commits": week.commits}
            )
        )
