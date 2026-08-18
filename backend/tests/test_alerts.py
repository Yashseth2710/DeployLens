from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.repository import Repository
from app.models.user import User
from app.models.workflow import WorkflowRun
from app.services import alerts, github_api
from app.services.github_api import GitHubError, GitHubIssue

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


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Record what would have been sent instead of sending it."""
    sent: list[tuple[str, Any]] = []

    def create_issue(
        token: str, full_name: str, title: str, body: str, labels: list[str]
    ) -> GitHubIssue:
        sent.append(("create", title))
        return GitHubIssue(number=77, url=f"https://github.com/{full_name}/issues/77")

    def close_issue(token: str, full_name: str, number: int, comment: str) -> None:
        sent.append(("close", number))

    monkeypatch.setattr(github_api, "create_issue", create_issue)
    monkeypatch.setattr(github_api, "close_issue", close_issue)
    return sent


def add_runs(db: Session, repository: Repository, conclusions: list[str], *, first_id: int) -> None:
    for index, conclusion in enumerate(conclusions):
        db.add(
            WorkflowRun(
                repository_id=repository.id,
                github_run_id=first_id + index,
                workflow_name="Nightly",
                branch="main",
                commit_sha=f"{index:040x}",
                status="completed",
                conclusion=conclusion,
                duration_seconds=60,
                started_at=NOW - timedelta(hours=index + 1),
                completed_at=NOW - timedelta(hours=index + 1) + timedelta(minutes=1),
                html_url="https://example.invalid/run",
            )
        )
    db.flush()


def open_alerts(db: Session, repository: Repository) -> list[Alert]:
    return list(
        db.scalars(
            select(Alert).where(Alert.repository_id == repository.id, Alert.resolved_at.is_(None))
        )
    )


def test_dry_run_decides_without_writing_anything(
    db: Session, repository: Repository, github: list[tuple[str, Any]]
) -> None:
    add_runs(db, repository, ["failure"] * 6, first_id=1000)

    run = alerts.sweep(db, 14, dry_run=True)

    assert run.raised == 1
    assert run.dry_run is True
    assert github == []
    assert open_alerts(db, repository) == []
    assert run.actions[0].title
    assert run.actions[0].body


def test_a_broken_workflow_raises_one_issue(
    db: Session, repository: Repository, github: list[tuple[str, Any]]
) -> None:
    """A streak and a chronic failure describe the same broken workflow. It is one
    problem and earns one issue, not one per way of describing it."""
    add_runs(db, repository, ["failure"] * 6, first_id=1100)

    run = alerts.sweep(db, 14, dry_run=False)

    assert run.raised == 1
    assert len(github) == 1
    stored = open_alerts(db, repository)
    assert len(stored) == 1
    assert stored[0].issue_number == 77


def test_a_standing_problem_is_not_reported_twice(
    db: Session, repository: Repository, github: list[tuple[str, Any]]
) -> None:
    add_runs(db, repository, ["failure"] * 6, first_id=1200)
    alerts.sweep(db, 14, dry_run=False)
    github.clear()

    run = alerts.sweep(db, 14, dry_run=False)

    assert run.raised == 0
    assert run.unchanged == 1
    assert github == []
    assert len(open_alerts(db, repository)) == 1


def test_recovery_closes_the_issue_and_keeps_the_record(
    db: Session, repository: Repository, github: list[tuple[str, Any]]
) -> None:
    add_runs(db, repository, ["failure"] * 6, first_id=1300)
    alerts.sweep(db, 14, dry_run=False)

    db.query(WorkflowRun).filter(WorkflowRun.repository_id == repository.id).delete()
    add_runs(db, repository, ["success"] * 8, first_id=1400)
    github.clear()

    run = alerts.sweep(db, 14, dry_run=False)

    assert run.resolved == 1
    assert github == [("close", 77)]
    assert open_alerts(db, repository) == []
    resolved = db.scalars(select(Alert).where(Alert.resolved_at.is_not(None))).all()
    assert len(resolved) == 1


def test_the_same_problem_returning_is_raised_again(
    db: Session, repository: Repository, github: list[tuple[str, Any]]
) -> None:
    """A resolved alert keeps its row, so the partial unique index has to allow the
    same subject to be raised a second time."""
    add_runs(db, repository, ["failure"] * 6, first_id=1500)
    alerts.sweep(db, 14, dry_run=False)
    db.query(WorkflowRun).filter(WorkflowRun.repository_id == repository.id).delete()
    add_runs(db, repository, ["success"] * 8, first_id=1600)
    alerts.sweep(db, 14, dry_run=False)

    db.query(WorkflowRun).filter(WorkflowRun.repository_id == repository.id).delete()
    add_runs(db, repository, ["failure"] * 6, first_id=1700)
    run = alerts.sweep(db, 14, dry_run=False)

    assert run.raised == 1
    both = db.scalars(select(Alert).where(Alert.repository_id == repository.id)).all()
    assert len(both) == 2


def test_an_occasional_failure_is_not_worth_an_issue(
    db: Session, repository: Repository, github: list[tuple[str, Any]]
) -> None:
    """One failure in twelve is flaky, not broken. Alerting on it is how an alerting
    system gets muted."""
    add_runs(db, repository, ["success"] * 11 + ["failure"], first_id=1800)

    run = alerts.sweep(db, 14, dry_run=False)

    assert run.raised == 0
    assert github == []


def test_github_refusing_one_repository_does_not_stop_the_sweep(
    db: Session, repository: Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: Any, **kwargs: Any) -> GitHubIssue:
        raise GitHubError("archived repository")

    monkeypatch.setattr(github_api, "create_issue", refuse)
    add_runs(db, repository, ["failure"] * 6, first_id=1900)

    run = alerts.sweep(db, 14, dry_run=False)

    assert run.failed == 1
    assert run.raised == 0
    assert open_alerts(db, repository) == []


def test_preview_endpoint_reports_without_filing(
    client: TestClient, signed_in: User, db: Session, repository: Repository, github: list[Any]
) -> None:
    add_runs(db, repository, ["failure"] * 6, first_id=2000)

    response = client.post("/api/alerts/preview?days=14")

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["raised"] == 1
    assert body["actions"][0]["title"]
    assert github == []


def test_alerts_endpoint_requires_signing_in(client: TestClient) -> None:
    assert client.get("/api/alerts").status_code == 401
    assert client.post("/api/alerts/preview").status_code == 401
