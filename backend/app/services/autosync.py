from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.user import User
from app.services import history_sync, tokens, workflow_sync
from app.services.github_api import GitHubAuthExpiredError, GitHubError

# How stale a repository is allowed to get before it is pulled again while somebody is
# watching. Five seconds is fast enough that a run appearing on GitHub and appearing here
# feel like the same event.
#
# The cost is three requests per repository per pass — runs, deployments, pull requests —
# which is only affordable because a deployment already recorded in a final state is
# never re-read. That fix matters more than this number: without it a repository with
# thirty deployments cost thirty one requests a pass and no window would have been safe.
# At three requests, an open tab on two repositories spends about 4300 of the 5000 an
# hour a token allows. A third repository needs this raised.
WATCHING_MAX_AGE = timedelta(seconds=5)

# The scheduled run has no browser watching it, so it refreshes everything it finds
# rather than deciding what looks interesting.
CRON_MAX_AGE = timedelta(minutes=30)

# A pull request changes state the instant somebody merges it, and a board showing a
# merged one as open is wrong rather than merely late — so it runs at the same window as
# everything else.
PULL_REQUEST_MAX_AGE = timedelta(seconds=5)

# Commit totals are weekly buckets that GitHub recomputes on its own schedule, so asking
# more often than this reads the same numbers back.
COMMIT_STATS_MAX_AGE = timedelta(minutes=30)


@dataclass(frozen=True)
class RefreshReport:
    synced: int
    skipped: int
    failed: int
    runs_added: int
    deployments_added: int
    pull_requests: int
    last_synced_at: datetime | None


def refresh_user(db: Session, user: User, access_token: str) -> RefreshReport:
    """Pull whatever has gone stale for one signed-in user.

    This is what makes the product current without anybody pressing anything: the page
    asks for the activity board on a timer, and asking is itself what triggers the pull.
    Throttling lives here rather than in the client so a second open tab costs nothing,
    and it is the only reason there is no manual control — a throttle short enough to
    feel immediate leaves nothing for a button to do.
    """
    repositories = list(
        db.scalars(select(Repository).where(Repository.user_id == user.id).order_by(Repository.id))
    )
    return _refresh(db, repositories, access_token, max_age=WATCHING_MAX_AGE)


def refresh_everyone(db: Session) -> RefreshReport:
    """The scheduled sweep, for the hours when nobody has the page open. Runs per user so
    one revoked token cannot stop the rest from being collected."""
    totals = RefreshReport(0, 0, 0, 0, 0, 0, None)
    for user in db.scalars(select(User)):
        try:
            token = tokens.access_token_for(db, user)
        except (ValueError, GitHubAuthExpiredError):
            # A token we cannot read or renew is a sign-in problem for that user alone.
            continue
        repositories = list(db.scalars(select(Repository).where(Repository.user_id == user.id)))
        try:
            totals = _add(totals, _refresh(db, repositories, token, max_age=CRON_MAX_AGE))
        except GitHubAuthExpiredError:
            # Only this user has to sign in again; the sweep collects for everybody else.
            continue
    return totals


def _refresh(
    db: Session,
    repositories: list[Repository],
    access_token: str,
    *,
    max_age: timedelta,
) -> RefreshReport:
    synced = skipped = failed = runs_added = deployments_added = pull_requests = 0

    for repository in repositories:
        if not _is_stale(repository, max_age):
            skipped += 1
            continue
        try:
            result = workflow_sync.sync_repository(db, repository, access_token)
        except GitHubAuthExpiredError:
            # Not a failure to count and retry: nothing will succeed until the user signs
            # in again, and every pass until then would silently show stale data as live.
            db.commit()
            raise
        except GitHubError:
            # A rate limit or a repository that has since been deleted must not take the
            # rest of the sweep down with it; the next pass tries again.
            failed += 1
            continue

        runs_added += result.runs_added
        deployments_added += result.deployments_added + result.provider_deployments
        repository.last_synced_at = datetime.now(UTC)
        synced += 1

        # Pull requests and commit totals run on their own clocks, and on each other's
        # too: a merge must show up promptly, a year of weekly commit counts need not.
        with_commits = _is_older_than(repository.commits_synced_at, COMMIT_STATS_MAX_AGE)
        if _is_older_than(repository.history_synced_at, PULL_REQUEST_MAX_AGE) or with_commits:
            try:
                history = history_sync.sync_history(
                    db, repository, access_token, with_commits=with_commits
                )
            except GitHubAuthExpiredError:
                db.commit()
                raise
            except GitHubError:
                continue
            pull_requests += history.pull_requests_seen
            repository.history_synced_at = datetime.now(UTC)
            if with_commits:
                repository.commits_synced_at = datetime.now(UTC)

    db.commit()
    return RefreshReport(
        synced=synced,
        skipped=skipped,
        failed=failed,
        runs_added=runs_added,
        deployments_added=deployments_added,
        pull_requests=pull_requests,
        last_synced_at=_oldest(repositories),
    )


def _is_stale(repository: Repository, max_age: timedelta) -> bool:
    if repository.last_synced_at is None:
        return True
    return datetime.now(UTC) - repository.last_synced_at >= max_age


def _is_older_than(stamp: datetime | None, max_age: timedelta) -> bool:
    return stamp is None or datetime.now(UTC) - stamp >= max_age


def _oldest(repositories: list[Repository]) -> datetime | None:
    """The freshness of the whole picture is the freshness of its stalest part, so the
    line the user reads is not made optimistic by one repository that just updated."""
    stamps = [repository.last_synced_at for repository in repositories if repository.last_synced_at]
    return min(stamps) if stamps else None


def _add(left: RefreshReport, right: RefreshReport) -> RefreshReport:
    return RefreshReport(
        synced=left.synced + right.synced,
        skipped=left.skipped + right.skipped,
        failed=left.failed + right.failed,
        runs_added=left.runs_added + right.runs_added,
        deployments_added=left.deployments_added + right.deployments_added,
        pull_requests=left.pull_requests + right.pull_requests,
        last_synced_at=min(
            [stamp for stamp in (left.last_synced_at, right.last_synced_at) if stamp],
            default=None,
        ),
    )
