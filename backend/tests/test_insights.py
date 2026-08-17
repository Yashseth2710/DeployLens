from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.user import User
from app.models.workflow import WorkflowRun

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
    workflow: str = "CI",
    branch: str | None = "main",
    conclusion: str = "success",
    commit: str | None = None,
    hours_ago: float = 0,
    duration: int = 60,
) -> WorkflowRun:
    record = WorkflowRun(
        repository_id=repository.id,
        github_run_id=github_run_id,
        workflow_name=workflow,
        branch=branch,
        commit_sha=commit,
        status="completed",
        conclusion=conclusion,
        duration_seconds=duration,
        started_at=NOW - timedelta(hours=hours_ago),
        html_url=f"https://github.com/octocat/deploylens/actions/runs/{github_run_id}",
    )
    db.add(record)
    db.flush()
    return record


def findings(client: TestClient, repository: Repository, **params) -> list[dict]:
    response = client.get(f"/api/analytics/repositories/{repository.id}/insights", params=params)
    assert response.status_code == 200
    return response.json()["findings"]


def of_kind(found: list[dict], kind: str) -> list[dict]:
    return [finding for finding in found if finding["kind"] == kind]


def test_a_workflow_that_passed_and_failed_on_one_commit_is_flaky(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    """The code did not change between those two runs, so the pipeline is what differed."""
    add_run(db, repository, github_run_id=7001, commit="a" * 40, conclusion="failure", hours_ago=2)
    add_run(db, repository, github_run_id=7002, commit="a" * 40, conclusion="success", hours_ago=1)

    flaky = of_kind(findings(client, repository), "flaky")

    assert len(flaky) == 1
    assert flaky[0]["subject"] == "CI"
    assert "same commit" in flaky[0]["detail"]
    assert flaky[0]["run_url"].endswith("/7001")


def test_a_commit_that_only_ever_failed_is_not_flaky(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    """Failing twice on the same commit is a broken commit, which is a different
    problem from a pipeline that cannot make its mind up."""
    add_run(db, repository, github_run_id=7011, commit="b" * 40, conclusion="failure", hours_ago=2)
    add_run(db, repository, github_run_id=7012, commit="b" * 40, conclusion="failure", hours_ago=1)

    assert of_kind(findings(client, repository), "flaky") == []


def test_a_workflow_failing_a_third_of_the_time_is_chronic(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for index in range(8):
        add_run(
            db,
            repository,
            github_run_id=7100 + index,
            conclusion="failure" if index < 3 else "success",
            hours_ago=index,
        )

    chronic = of_kind(findings(client, repository), "chronic")

    assert len(chronic) == 1
    assert chronic[0]["failed"] == 3
    assert chronic[0]["runs"] == 8
    assert "38%" in chronic[0]["detail"]


def test_a_workflow_fixed_a_while_ago_is_not_reported_as_broken(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    """Its failure rate for the window stays high for as long as the window is open.
    Sending somebody to read logs that were already dealt with is the failure mode."""
    for index in range(5):
        add_run(
            db, repository, github_run_id=7200 + index, conclusion="failure", hours_ago=400 + index
        )
    for index in range(10):
        add_run(db, repository, github_run_id=7220 + index, conclusion="success", hours_ago=index)

    assert of_kind(findings(client, repository), "chronic") == []


def test_consecutive_failures_right_now_are_a_streak(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for index in range(6):
        add_run(
            db, repository, github_run_id=7300 + index, conclusion="success", hours_ago=10 + index
        )
    for index in range(4):
        add_run(db, repository, github_run_id=7320 + index, conclusion="failure", hours_ago=index)

    found = findings(client, repository)
    streaks = of_kind(found, "streak")

    assert len(streaks) == 1
    assert streaks[0]["failed"] == 4
    assert "4 runs in a row" in streaks[0]["detail"]
    # A streak is the most urgent thing the sheet can say, so it leads.
    assert found[0]["kind"] == "streak"


def test_two_failures_in_a_row_are_not_a_streak(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    add_run(db, repository, github_run_id=7401, conclusion="failure", hours_ago=0)
    add_run(db, repository, github_run_id=7402, conclusion="failure", hours_ago=1)
    for index in range(6):
        add_run(
            db, repository, github_run_id=7410 + index, conclusion="success", hours_ago=5 + index
        )

    assert of_kind(findings(client, repository), "streak") == []


def test_a_workflow_taking_much_longer_than_before_is_a_slowdown(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for index in range(8):
        add_run(db, repository, github_run_id=7500 + index, hours_ago=20 + index, duration=60)
    for index in range(8):
        add_run(db, repository, github_run_id=7520 + index, hours_ago=index, duration=240)

    slowdowns = of_kind(findings(client, repository), "slowdown")

    assert len(slowdowns) == 1
    assert slowdowns[0]["detail"] == "1.0m to 4.0m, 4.0 times slower"


def test_a_steady_workflow_is_not_reported_as_slowing(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for index in range(16):
        add_run(db, repository, github_run_id=7600 + index, hours_ago=index, duration=60 + index)

    assert of_kind(findings(client, repository), "slowdown") == []


def test_failures_concentrated_on_one_branch_are_named(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for index in range(6):
        add_run(db, repository, github_run_id=7700 + index, branch="main", hours_ago=index)
    for index in range(5):
        add_run(
            db,
            repository,
            github_run_id=7720 + index,
            branch="redesign",
            conclusion="failure" if index < 4 else "success",
            hours_ago=index,
        )

    branches = of_kind(findings(client, repository), "branch")

    assert [finding["subject"] for finding in branches] == ["redesign"]
    assert branches[0]["detail"] == "4 failures in 5 runs"


def test_a_handful_of_runs_is_not_a_pattern(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    """Three failures out of four runs is worth saying; one out of one is a bad
    afternoon, and a project's first day should not open with an accusation."""
    add_run(db, repository, github_run_id=7801, conclusion="failure")

    assert of_kind(findings(client, repository), "chronic") == []
    assert of_kind(findings(client, repository), "branch") == []


def test_runs_still_in_flight_are_not_read_as_verdicts(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for index in range(6):
        add_run(db, repository, github_run_id=7900 + index, conclusion="cancelled", hours_ago=index)

    assert findings(client, repository) == []


def test_a_healthy_project_reports_nothing(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for index in range(12):
        add_run(db, repository, github_run_id=8000 + index, commit=f"{index:040d}", hours_ago=index)

    assert findings(client, repository) == []


def test_findings_stay_inside_the_window(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for index in range(6):
        add_run(
            db,
            repository,
            github_run_id=8100 + index,
            conclusion="failure",
            hours_ago=24 * 40 + index,
        )

    assert findings(client, repository, days=7) == []
    assert findings(client, repository, days=365) != []


def test_the_dashboard_band_names_only_projects_with_something_wrong(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    healthy = Repository(
        user_id=signed_in.id,
        github_repo_id=910002,
        name="notes",
        full_name="octocat/notes",
        owner="octocat",
        default_branch="main",
        github_url="https://github.com/octocat/notes",
    )
    db.add(healthy)
    db.flush()
    for index in range(6):
        add_run(db, healthy, github_run_id=8200 + index, hours_ago=index)
    for index in range(5):
        add_run(db, repository, github_run_id=8220 + index, conclusion="failure", hours_ago=index)

    body = client.get("/api/analytics/attention").json()

    assert [row["full_name"] for row in body["repositories"]] == ["octocat/deploylens"]
    # Two lines a project keeps the band a summary rather than a second report.
    assert len(body["repositories"][0]["findings"]) <= 2


def test_insights_are_scoped_to_the_signed_in_user(
    client: TestClient, db: Session, signed_in: User
):
    stranger = User(github_id=99456, username="stranger", access_token_encrypted="x")
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
    for index in range(5):
        add_run(db, theirs, github_run_id=8300 + index, conclusion="failure", hours_ago=index)

    assert client.get(f"/api/analytics/repositories/{theirs.id}/insights").status_code == 404
    assert client.get("/api/analytics/attention").json()["repositories"] == []


def test_insights_need_a_session(client: TestClient, repository: Repository):
    assert client.get(f"/api/analytics/repositories/{repository.id}/insights").status_code == 401
    assert client.get("/api/analytics/attention").status_code == 401
