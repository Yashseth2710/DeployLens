from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_token
from app.models.repository import Repository
from app.models.user import User
from app.services import activity, workflow_sync
from app.services.github_api import GitHubError

# How stale a repository is allowed to get before it is pulled again. A repository with
# something running changes by the second and is worth the request; one that has been
# quiet for a week is not, and every avoided call is GitHub rate limit and database wake
# time we do not spend.
LIVE_MAX_AGE = timedelta(seconds=25)
IDLE_MAX_AGE = timedelta(minutes=3)

# The scheduled run has no browser watching it, so it refreshes everything it finds
# rather than deciding what looks interesting.
CRON_MAX_AGE = timedelta(minutes=30)


@dataclass(frozen=True)
class RefreshReport:
    synced: int
    skipped: int
    failed: int
    runs_added: int
    deployments_added: int
    last_synced_at: datetime | None


def refresh_user(db: Session, user: User, access_token: str, force: bool = False) -> RefreshReport:
    """Pull whatever has gone stale for one signed-in user.

    This is what makes the product current without anybody pressing anything: the page
    asks for the activity board on a timer, and asking is itself what triggers the pull.
    Throttling lives here rather than in the client so a second open tab costs nothing.
    """
    repositories = list(
        db.scalars(select(Repository).where(Repository.user_id == user.id).order_by(Repository.id))
    )
    return _refresh(db, repositories, access_token, force=force, idle_max_age=IDLE_MAX_AGE)


def refresh_everyone(db: Session) -> RefreshReport:
    """The scheduled sweep, for the hours when nobody has the page open. Runs per user so
    one revoked token cannot stop the rest from being collected."""
    totals = RefreshReport(0, 0, 0, 0, 0, None)
    for user in db.scalars(select(User)):
        try:
            token = decrypt_token(user.access_token_encrypted)
        except ValueError:
            # A token we can no longer read is a sign-in problem for that user alone.
            continue
        repositories = list(db.scalars(select(Repository).where(Repository.user_id == user.id)))
        totals = _add(
            totals, _refresh(db, repositories, token, force=False, idle_max_age=CRON_MAX_AGE)
        )
    return totals


def _refresh(
    db: Session,
    repositories: list[Repository],
    access_token: str,
    *,
    force: bool,
    idle_max_age: timedelta,
) -> RefreshReport:
    synced = skipped = failed = runs_added = deployments_added = 0

    for repository in repositories:
        if not force and not _is_stale(db, repository, idle_max_age):
            skipped += 1
            continue
        try:
            result = workflow_sync.sync_repository(db, repository, access_token)
        except GitHubError:
            # A rate limit or a repository that has since been deleted must not take the
            # rest of the sweep down with it; the next pass tries again.
            failed += 1
            continue

        runs_added += result.runs_added
        deployments_added += result.deployments_added + result.provider_deployments
        repository.last_synced_at = datetime.now(UTC)
        synced += 1

    db.commit()
    return RefreshReport(
        synced=synced,
        skipped=skipped,
        failed=failed,
        runs_added=runs_added,
        deployments_added=deployments_added,
        last_synced_at=_oldest(repositories),
    )


def _is_stale(db: Session, repository: Repository, idle_max_age: timedelta) -> bool:
    if repository.last_synced_at is None:
        return True
    max_age = LIVE_MAX_AGE if activity.has_live_run(db, repository.id) else idle_max_age
    return datetime.now(UTC) - repository.last_synced_at >= max_age


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
        last_synced_at=min(
            [stamp for stamp in (left.last_synced_at, right.last_synced_at) if stamp],
            default=None,
        ),
    )
