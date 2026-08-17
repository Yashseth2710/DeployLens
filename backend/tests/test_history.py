from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.history import CommitWeek, PullRequest
from app.models.repository import Repository
from app.models.user import User
from app.services import history_sync, metrics
from app.services.github_api import GitHubCommitWeek, GitHubPullRequest

NOW = datetime.now(UTC)


@pytest.fixture
def repository(db: Session, user: User) -> Repository:
    record = Repository(
        user_id=user.id,
        github_repo_id=920001,
        name="deploylens",
        full_name="octocat/deploylens",
        owner="octocat",
        default_branch="main",
        github_url="https://github.com/octocat/deploylens",
    )
    db.add(record)
    db.flush()
    return record


def pull_request(
    number: int,
    *,
    state: str = "closed",
    opened_days_ago: float = 3,
    merged_days_ago: float | None = 1,
    closed_days_ago: float | None = 1,
) -> GitHubPullRequest:
    return GitHubPullRequest(
        number=number,
        title=f"Pull request {number}",
        author="octocat",
        state=state,
        draft=False,
        head_branch=f"feature/{number}",
        base_branch="main",
        html_url=f"https://github.com/octocat/deploylens/pull/{number}",
        opened_at=NOW - timedelta(days=opened_days_ago),
        updated_at=NOW,
        merged_at=None if merged_days_ago is None else NOW - timedelta(days=merged_days_ago),
        closed_at=None if closed_days_ago is None else NOW - timedelta(days=closed_days_ago),
    )


def test_a_resync_updates_a_pull_request_that_has_since_merged(db: Session, repository: Repository):
    history_sync.record_pull_requests(
        db, repository, [pull_request(1, state="open", merged_days_ago=None, closed_days_ago=None)]
    )
    db.flush()
    history_sync.record_pull_requests(db, repository, [pull_request(1)])
    db.flush()

    stored = db.scalars(
        PullRequest.__table__.select().where(PullRequest.repository_id == repository.id)
    ).all()

    assert len(stored) == 1


def test_merged_and_abandoned_are_told_apart(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    """GitHub calls both of these "closed". The difference between work that shipped and
    work that was dropped is the whole reason to collect pull requests."""
    history_sync.record_pull_requests(
        db,
        repository,
        [
            pull_request(1),
            pull_request(2, merged_days_ago=None),
            pull_request(3, state="open", merged_days_ago=None, closed_days_ago=None),
        ],
    )
    db.commit()

    rows = client.get("/api/pull-requests").json()
    by_number = {row["number"]: row["outcome"] for row in rows}

    assert by_number == {1: "merged", 2: "abandoned", 3: "open"}
    assert client.get("/api/pull-requests", params={"state": "merged"}).json()[0]["number"] == 1
    assert client.get("/api/pull-requests", params={"state": "abandoned"}).json()[0]["number"] == 2


def test_review_metrics_count_merges_by_when_they_landed(
    db: Session, repository: Repository, user: User
):
    """A pull request opened before the window and merged inside it is a merge this
    month. Counting it only by when it opened would hide the work that just landed."""
    history_sync.record_pull_requests(
        db,
        repository,
        [
            pull_request(1, opened_days_ago=90, merged_days_ago=2),
            pull_request(2, opened_days_ago=5, merged_days_ago=None),
            pull_request(3, state="open", merged_days_ago=None, closed_days_ago=None),
        ],
    )
    db.flush()

    review = metrics.review_metrics(db, [repository.id], 30)

    assert review.merged == 1
    assert review.closed_unmerged == 1
    assert review.open_now == 1
    assert review.merge_rate == 50.0
    assert review.median_hours_to_merge is not None


def test_commit_weeks_are_overwritten_because_this_week_is_not_finished(
    db: Session, repository: Repository
):
    week = (NOW - timedelta(days=2)).date()
    history_sync.record_commit_weeks(db, repository, [GitHubCommitWeek(week_start=week, commits=3)])
    db.flush()
    history_sync.record_commit_weeks(db, repository, [GitHubCommitWeek(week_start=week, commits=9)])
    db.flush()

    stored = db.scalars(
        CommitWeek.__table__.select().where(CommitWeek.repository_id == repository.id)
    ).all()
    review = metrics.review_metrics(db, [repository.id], 30)

    assert len(stored) == 1
    assert review.commits == 9


def test_commit_history_reports_the_earliest_week_it_holds(db: Session, repository: Repository):
    """The "earliest available data" disclosure: the window is 30 days, but what we can
    see reaches further back, and saying so is what stops the page overclaiming."""
    history_sync.record_commit_weeks(
        db,
        repository,
        [
            GitHubCommitWeek(week_start=(NOW - timedelta(days=300)).date(), commits=12),
            GitHubCommitWeek(week_start=(NOW - timedelta(days=3)).date(), commits=4),
        ],
    )
    db.flush()

    review = metrics.review_metrics(db, [repository.id], 30)

    assert review.commits == 4
    assert review.first_commit_week is not None
    assert review.first_commit_week < (NOW - timedelta(days=200)).date()


def test_pull_requests_of_another_user_are_not_listed(
    client: TestClient, db: Session, signed_in: User
):
    stranger = User(github_id=99555, username="stranger", access_token_encrypted="x")
    db.add(stranger)
    db.flush()
    theirs = Repository(
        user_id=stranger.id,
        github_repo_id=920777,
        name="secret",
        full_name="stranger/secret",
        owner="stranger",
        default_branch="main",
        github_url="https://github.com/stranger/secret",
    )
    db.add(theirs)
    db.flush()
    history_sync.record_pull_requests(db, theirs, [pull_request(1)])
    db.commit()

    assert client.get("/api/pull-requests").json() == []


def test_commit_stats_are_skipped_when_only_pull_requests_are_due(
    db: Session, repository: Repository, monkeypatch: pytest.MonkeyPatch
):
    """A merge has to appear promptly; a year of weekly commit counts is the same year
    it was a minute ago. Asking for both on the fast cadence would double the cost of
    every pass to re-read numbers that had not moved."""
    asked: list[str] = []

    monkeypatch.setattr(
        history_sync.github_api,
        "list_pull_requests",
        lambda token, name, pages=1: asked.append("pulls") or [],
        raising=True,
    )
    monkeypatch.setattr(
        history_sync.github_api,
        "commit_activity",
        lambda token, name: asked.append("commits") or [],
        raising=True,
    )

    history_sync.sync_history(db, repository, "token", with_commits=False)

    assert asked == ["pulls"]


def test_a_merge_is_collected_on_the_next_pass(
    db: Session, user: User, repository: Repository, monkeypatch: pytest.MonkeyPatch
):
    """The defect this cadence exists to prevent: a pull request merged moments ago
    still reading as open because nothing had asked GitHub since. Commit stats stay on
    their own window and must not be pulled along with it."""
    from app.services import autosync

    repository.last_synced_at = datetime.now(UTC) - timedelta(minutes=5)
    repository.history_synced_at = datetime.now(UTC) - timedelta(minutes=5)
    repository.commits_synced_at = datetime.now(UTC)
    db.flush()

    monkeypatch.setattr(
        autosync.workflow_sync,
        "fetch",
        lambda token, full_name, pages, per_page, settled_ids: _no_runs(),
        raising=True,
    )
    monkeypatch.setattr(
        history_sync.github_api,
        "list_pull_requests",
        lambda token, name, pages=1: [pull_request(7)],
        raising=True,
    )
    monkeypatch.setattr(
        history_sync.github_api, "commit_activity", _should_not_be_asked, raising=True
    )

    report = autosync.refresh_user(db, user, "token")

    assert report.pull_requests == 1
    stored = db.scalars(
        PullRequest.__table__.select().where(PullRequest.repository_id == repository.id)
    ).all()
    assert len(stored) == 1


def _no_runs():
    from app.services.workflow_sync import RunPayload

    return RunPayload(runs=[], deployments=[])


def _should_not_be_asked(token: str, name: str):
    raise AssertionError("commit stats were collected on the pull request cadence")
