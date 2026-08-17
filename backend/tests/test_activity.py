from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.user import User
from app.models.workflow import Deployment, WorkflowRun
from app.services import activity, autosync
from app.services.github_api import GitHubRateLimitError

NOW = datetime.now(UTC)


@pytest.fixture
def repository(db: Session, user: User) -> Repository:
    record = Repository(
        user_id=user.id,
        github_repo_id=910001,
        name="deploylens",
        full_name="octocat/deploylens",
        owner="octocat",
        default_branch="main",
        github_url="https://github.com/octocat/deploylens",
    )
    db.add(record)
    db.flush()
    return record


def add_run(
    db: Session,
    repository: Repository,
    *,
    github_run_id: int,
    status: str = "completed",
    conclusion: str | None = "success",
    minutes_ago: float = 1,
) -> WorkflowRun:
    started = NOW - timedelta(minutes=minutes_ago)
    record = WorkflowRun(
        repository_id=repository.id,
        github_run_id=github_run_id,
        workflow_name="CI",
        branch="main",
        status=status,
        conclusion=conclusion,
        started_at=started,
        completed_at=None if status != "completed" else started + timedelta(seconds=90),
    )
    db.add(record)
    db.flush()
    return record


def test_board_carries_running_and_just_settled_items(
    db: Session, user: User, repository: Repository
):
    """A run that has just passed stays on the board briefly. Without the grace period
    the answer to "did it work" disappears at the moment it arrives."""
    add_run(db, repository, github_run_id=7001, status="in_progress", conclusion=None)
    add_run(db, repository, github_run_id=7002, conclusion="failure", minutes_ago=2)
    add_run(db, repository, github_run_id=7003, minutes_ago=60 * 24)

    board = activity.board(db, user.id)
    ids = {item.status for item in board}

    assert len(board) == 2
    assert "in_progress" in ids
    # Live leads, whatever the timestamps say.
    assert board[0].live is True
    assert board[1].live is False
    assert board[1].conclusion == "failure"


def test_board_ignores_another_users_repositories(db: Session, user: User, repository: Repository):
    stranger = User(github_id=99321, username="stranger", access_token_encrypted="x")
    db.add(stranger)
    db.flush()
    theirs = Repository(
        user_id=stranger.id,
        github_repo_id=910777,
        name="secret",
        full_name="stranger/secret",
        owner="stranger",
        default_branch="main",
        github_url="https://github.com/stranger/secret",
    )
    db.add(theirs)
    db.flush()
    add_run(db, theirs, github_run_id=7101, status="in_progress", conclusion=None)

    assert activity.board(db, user.id) == []


def test_a_repository_with_a_run_in_flight_is_checked_far_more_often(
    db: Session, repository: Repository
):
    """The whole point of the throttle: watch closely while something is happening,
    and leave a quiet repository alone."""
    repository.last_synced_at = NOW - timedelta(seconds=40)
    db.flush()

    assert autosync._is_stale(db, repository, autosync.IDLE_MAX_AGE) is False

    add_run(db, repository, github_run_id=7201, status="in_progress", conclusion=None)

    assert autosync._is_stale(db, repository, autosync.IDLE_MAX_AGE) is True


def test_refresh_skips_repositories_that_were_just_read(
    db: Session, user: User, repository: Repository, monkeypatch: pytest.MonkeyPatch
):
    repository.last_synced_at = NOW
    db.flush()
    monkeypatch.setattr(autosync.workflow_sync, "sync_repository", _fail_if_called, raising=True)

    report = autosync.refresh_user(db, user, "token")

    assert report.skipped == 1
    assert report.synced == 0


def test_force_ignores_the_throttle(
    db: Session, user: User, repository: Repository, monkeypatch: pytest.MonkeyPatch
):
    """What "Sync now" is for: somebody wants to be sure, not to wait for a timer."""
    repository.last_synced_at = NOW
    db.flush()
    monkeypatch.setattr(autosync.workflow_sync, "sync_repository", _synced_nothing, raising=True)

    report = autosync.refresh_user(db, user, "token", force=True)

    assert report.synced == 1
    assert report.skipped == 0
    assert repository.last_synced_at is not None


def test_one_unreadable_repository_does_not_stop_the_rest(
    db: Session, user: User, repository: Repository, monkeypatch: pytest.MonkeyPatch
):
    second = Repository(
        user_id=user.id,
        github_repo_id=910002,
        name="other",
        full_name="octocat/other",
        owner="octocat",
        default_branch="main",
        github_url="https://github.com/octocat/other",
    )
    db.add(second)
    db.flush()

    calls: list[str] = []

    def flaky(db_, repo, token):
        calls.append(repo.full_name)
        if repo.full_name == "octocat/deploylens":
            raise GitHubRateLimitError("rate limited")
        return _synced_nothing(db_, repo, token)

    monkeypatch.setattr(autosync.workflow_sync, "sync_repository", flaky, raising=True)

    report = autosync.refresh_user(db, user, "token")

    assert len(calls) == 2
    assert report.failed == 1
    assert report.synced == 1


def test_activity_endpoint_reports_a_faster_poll_while_something_runs(
    client: TestClient,
    db: Session,
    signed_in: User,
    repository: Repository,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(autosync.workflow_sync, "sync_repository", _synced_nothing, raising=True)
    add_run(db, repository, github_run_id=7301, status="in_progress", conclusion=None)

    body = client.post("/api/activity").json()

    assert body["live_count"] == 1
    assert body["poll_seconds"] < 30
    assert body["items"][0]["live"] is True


def test_activity_endpoint_slows_down_when_nothing_is_running(
    client: TestClient,
    db: Session,
    signed_in: User,
    repository: Repository,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(autosync.workflow_sync, "sync_repository", _synced_nothing, raising=True)

    body = client.post("/api/activity").json()

    assert body["live_count"] == 0
    assert body["poll_seconds"] >= 30


def test_a_provider_deployment_still_building_reads_as_live(
    db: Session, user: User, repository: Repository
):
    db.add(
        Deployment(
            repository_id=repository.id,
            github_deployment_id=55501,
            environment="production",
            status="in_progress",
            branch="main",
            started_at=NOW - timedelta(seconds=30),
        )
    )
    db.flush()

    board = activity.board(db, user.id)

    assert len(board) == 1
    assert board[0].kind == "deploy"
    assert board[0].live is True
    assert board[0].title == "Deploy to production"


def _synced_nothing(db_: Session, repository: Repository, token: str):
    from app.services.workflow_sync import SyncResult

    return SyncResult(runs_seen=0, runs_added=0, deployments_added=0, provider_deployments=0)


def _fail_if_called(db_: Session, repository: Repository, token: str):
    raise AssertionError("a repository read moments ago should not be read again")
