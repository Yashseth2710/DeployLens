from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.user import User
from app.models.workflow import Deployment, WorkflowRun
from app.services import activity, autosync
from app.services.github_api import GitHubRateLimitError
from app.services.history_sync import HistoryPayload
from app.services.workflow_sync import RunPayload

NOW = datetime.now(UTC)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing in this file should reach GitHub.

    Pull requests ride along in the same pass as runs, and the endpoint hands its
    collection to a background task that opens a session of its own — which would write
    outside the transaction this test rolls back.
    """
    monkeypatch.setattr(
        autosync.history_sync,
        "fetch",
        lambda token, full_name, pages, with_commits: HistoryPayload(
            pull_requests=[], commit_weeks=[]
        ),
        raising=True,
    )
    monkeypatch.setattr(autosync, "collect_for", lambda user_id, token: None, raising=True)


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


def test_refresh_skips_repositories_that_were_just_read(
    db: Session, user: User, repository: Repository, monkeypatch: pytest.MonkeyPatch
):
    # Read at assertion time, not at import: the window is ten seconds, and a module
    # level constant is already stale by the time a full suite reaches this test.
    repository.last_synced_at = datetime.now(UTC)
    db.flush()
    monkeypatch.setattr(autosync.workflow_sync, "fetch", _fail_if_called, raising=True)

    report = autosync.refresh_user(db, user, "token")

    assert report.skipped == 1
    assert report.synced == 0


def test_a_repository_read_longer_ago_than_the_window_is_pulled_again(
    db: Session, user: User, repository: Repository, monkeypatch: pytest.MonkeyPatch
):
    """The throttle is what an open page feels as its refresh rate, so a repository
    older than it must be collected without anybody asking."""
    repository.last_synced_at = (
        datetime.now(UTC) - autosync.watching_interval(1) - timedelta(seconds=1)
    )
    db.flush()
    monkeypatch.setattr(autosync.workflow_sync, "fetch", _fetched_nothing, raising=True)

    report = autosync.refresh_user(db, user, "token")

    assert report.synced == 1
    assert report.skipped == 0


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

    def flaky(token, full_name, pages, per_page, settled_ids):
        calls.append(full_name)
        if full_name == "octocat/deploylens":
            raise GitHubRateLimitError("rate limited")
        return RunPayload(runs=[], deployments=[])

    monkeypatch.setattr(autosync.workflow_sync, "fetch", flaky, raising=True)

    report = autosync.refresh_user(db, user, "token")

    assert len(calls) == 2
    assert report.failed == 1
    assert report.synced == 1


def test_activity_endpoint_reports_the_live_board_and_its_poll_rate(
    client: TestClient,
    db: Session,
    signed_in: User,
    repository: Repository,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(autosync.workflow_sync, "fetch", _fetched_nothing, raising=True)
    add_run(db, repository, github_run_id=7301, status="in_progress", conclusion=None)

    body = client.post("/api/activity").json()

    assert body["live_count"] == 1
    assert body["poll_seconds"] == 5  # one repository fits the fastest window
    assert body["items"][0]["live"] is True


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


def test_the_window_widens_rather_than_outrunning_the_rate_limit(db: Session):
    """Fixed at five seconds this was correct for two repositories and quietly wrong for
    four: the page would keep asking and GitHub would start refusing, which reads as the
    app being broken rather than as a budget being exceeded."""
    assert autosync.watching_interval(1) == autosync.FASTEST_WATCHING
    assert autosync.watching_interval(10) > autosync.watching_interval(3)

    for count in (1, 3, 10):
        passes_per_hour = 3600 / autosync.watching_interval(count).total_seconds()
        assert passes_per_hour * count * autosync.REQUESTS_PER_PASS <= autosync.HOURLY_BUDGET + 1


def _fetched_nothing(token: str, full_name: str, pages: int, per_page: int, settled_ids):
    return RunPayload(runs=[], deployments=[])


def _fail_if_called(token: str, full_name: str, pages: int, per_page: int, settled_ids):
    raise AssertionError("a repository read moments ago should not be read again")
