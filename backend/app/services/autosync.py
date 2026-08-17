from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.repository import Repository
from app.models.user import User
from app.services import history_sync, tokens, workflow_sync
from app.services.github_api import GitHubAuthExpiredError, GitHubError

# The fastest we will collect while somebody is watching. Five seconds is close enough
# that a run appearing on GitHub and appearing here feel like the same event.
FASTEST_WATCHING = timedelta(seconds=5)

# Each pass spends this many requests per repository: runs, deployments, pull requests.
# It stays at three only because a deployment already recorded in a final state is never
# read again — without that a repository with thirty deployments cost thirty one requests
# a pass and no window would have been safe.
REQUESTS_PER_PASS = 3

# GitHub allows five thousand an hour per token. The rest is left for everything that is
# not this loop: connecting a repository, listing what is available, signing in.
HOURLY_BUDGET = 4200

# The scheduled run has no browser watching it, so it refreshes everything it finds
# rather than deciding what looks interesting.
CRON_MAX_AGE = timedelta(minutes=30)

# A pull request changes state the instant somebody merges it, and a board showing a
# merged one as open is wrong rather than merely late — so it rides the same pass as the
# runs rather than waiting for a window of its own.
PULL_REQUEST_MAX_AGE = timedelta(seconds=1)

# Commit totals are weekly buckets that GitHub recomputes on its own schedule, so asking
# more often than this reads the same numbers back.
COMMIT_STATS_MAX_AGE = timedelta(minutes=30)

# Enough to overlap every read a handful of repositories needs without opening a
# connection per repository to GitHub for somebody tracking dozens.
MAX_PARALLEL_READS = 12


@dataclass(frozen=True)
class CollectionState:
    """What the page needs to describe collection without waiting for any of it."""

    repositories: int
    failed: int
    last_synced_at: datetime | None


# One collection per user at a time. Polls arrive every few seconds and a pull takes
# longer than that, so without this a slow pass would be joined by the next one and both
# would write the same rows.
_collecting: set[UUID] = set()
_guard = Lock()


def collection_state(db: Session, user_id: UUID) -> CollectionState:
    rows = list(
        db.execute(select(Repository.last_synced_at).where(Repository.user_id == user_id)).scalars()
    )
    stamps = [stamp for stamp in rows if stamp is not None]
    return CollectionState(
        repositories=len(rows),
        # A repository we have never managed to read is the only failure the page can
        # see without the collection it is not waiting for.
        failed=sum(1 for stamp in rows if stamp is None),
        last_synced_at=min(stamps) if stamps else None,
    )


def collect_for(user_id: UUID, access_token: str) -> None:
    """Run a collection after the response has gone out.

    Its own session, because the request's is closed by the time this runs.
    """
    with _guard:
        if user_id in _collecting:
            return
        _collecting.add(user_id)

    try:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is None:
                return
            with suppress(GitHubAuthExpiredError):
                refresh_user(db, user, access_token)
    finally:
        with _guard:
            _collecting.discard(user_id)


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
    return _refresh(db, repositories, access_token, max_age=watching_interval(len(repositories)))


def watching_interval(repositories: int) -> timedelta:
    """The shortest window this many repositories can be collected at without spending
    more of GitHub's hourly allowance than we are willing to.

    Fixed at five seconds it would have been correct for two repositories and quietly
    wrong for four — the page would keep asking and GitHub would start refusing, which
    reads as the app being broken rather than as a budget being exceeded.
    """
    if repositories <= 0:
        return FASTEST_WATCHING
    affordable = repositories * REQUESTS_PER_PASS * 3600 / HOURLY_BUDGET
    return max(FASTEST_WATCHING, timedelta(seconds=affordable))


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
    synced = failed = runs_added = deployments_added = pull_requests = 0

    due = [repository for repository in repositories if _is_stale(repository, max_age)]
    skipped = len(repositories) - len(due)
    if not due:
        return RefreshReport(0, skipped, 0, 0, 0, 0, _oldest(repositories))

    # Every GitHub read for every repository at once. These are independent requests
    # whose cost is latency rather than work, so running them one after another made a
    # collection take as long as the sum of its round trips — twelve seconds for two
    # repositories, when the slowest single call is two.
    with ThreadPoolExecutor(max_workers=min(len(due) * 2, MAX_PARALLEL_READS)) as pool:
        work = {}
        for repository in due:
            pages, per_page, settled = workflow_sync.plan(db, repository)
            with_commits = _is_older_than(repository.commits_synced_at, COMMIT_STATS_MAX_AGE)
            work[repository.id] = (
                repository,
                with_commits,
                pool.submit(
                    workflow_sync.fetch,
                    access_token,
                    repository.full_name,
                    pages,
                    per_page,
                    settled,
                ),
                pool.submit(
                    history_sync.fetch,
                    access_token,
                    repository.full_name,
                    history_sync.plan(db, repository),
                    with_commits,
                ),
            )

        # Writing happens here, on one thread, because a session cannot be shared.
        for repository, with_commits, runs_future, history_future in work.values():
            try:
                result = workflow_sync.record(db, repository, runs_future.result())
            except GitHubAuthExpiredError:
                # Not a failure to count and retry: nothing will succeed until the user
                # signs in again, and every pass until then would show stale data as live.
                db.commit()
                raise
            except GitHubError:
                # A rate limit or a repository since deleted must not take the rest of
                # the sweep down with it; the next pass tries again.
                failed += 1
                continue

            runs_added += result.runs_added
            deployments_added += result.deployments_added + result.provider_deployments
            repository.last_synced_at = datetime.now(UTC)
            synced += 1

            try:
                history = history_sync.record(db, repository, history_future.result())
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
