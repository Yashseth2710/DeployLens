import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.user import User
from app.models.workflow import Deployment, WorkflowRun
from app.services.github_api import API_URL

FULL_NAME = "octocat/deploylens"


def run_payload(**overrides):
    payload = {
        "id": 55501,
        "name": "Deploy to production",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "actor": {"login": "octocat"},
        "run_started_at": "2026-08-16T10:00:00Z",
        "updated_at": "2026-08-16T10:04:30Z",
        "html_url": "https://github.com/octocat/deploylens/actions/runs/55501",
    }
    return payload | overrides


@pytest.fixture
def repository(db: Session, user: User) -> Repository:
    record = Repository(
        user_id=user.id,
        github_repo_id=900001,
        name="deploylens",
        full_name=FULL_NAME,
        owner="octocat",
        default_branch="main",
        github_url=f"https://github.com/{FULL_NAME}",
    )
    db.add(record)
    db.flush()
    return record


@pytest.fixture
def actions():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{API_URL}/repos/{FULL_NAME}/actions/runs").respond(
            json={"total_count": 1, "workflow_runs": [run_payload()]}
        )
        yield mock


def sync(client: TestClient, repository: Repository):
    return client.post(f"/api/repositories/{repository.id}/sync")


def test_sync_records_the_run_and_its_deployment(
    client: TestClient, db: Session, signed_in: User, repository: Repository, actions
):
    response = sync(client, repository)

    assert response.status_code == 200
    assert response.json() == {"runs_seen": 1, "runs_added": 1, "deployments_added": 1}

    run = db.scalar(select(WorkflowRun))
    assert run is not None
    assert run.github_run_id == 55501
    assert run.conclusion == "success"
    assert run.duration_seconds == 270

    deployment = db.scalar(select(Deployment))
    assert deployment is not None
    assert deployment.workflow_run_id == run.id
    assert deployment.environment == "production"
    assert deployment.author == "octocat"


def test_syncing_twice_updates_rather_than_duplicates(
    client: TestClient, db: Session, signed_in: User, repository: Repository, actions
):
    sync(client, repository)
    actions.get(f"{API_URL}/repos/{FULL_NAME}/actions/runs").respond(
        json={"workflow_runs": [run_payload(conclusion="failure")]}
    )

    second = sync(client, repository)

    assert second.json()["runs_added"] == 0
    assert len(db.scalars(select(WorkflowRun)).all()) == 1
    assert db.scalar(select(WorkflowRun)).conclusion == "failure"
    assert db.scalar(select(Deployment)).status == "failure"


def test_a_run_still_in_flight_has_no_duration(
    client: TestClient, db: Session, signed_in: User, repository: Repository, actions
):
    actions.get(f"{API_URL}/repos/{FULL_NAME}/actions/runs").respond(
        json={"workflow_runs": [run_payload(status="in_progress", conclusion=None)]}
    )

    sync(client, repository)

    run = db.scalar(select(WorkflowRun))
    assert run.status == "in_progress"
    assert run.completed_at is None
    assert run.duration_seconds is None
    assert db.scalar(select(Deployment)).status == "in_progress"


def test_test_and_lint_runs_are_recorded_but_are_not_deployments(
    client: TestClient, db: Session, signed_in: User, repository: Repository, actions
):
    actions.get(f"{API_URL}/repos/{FULL_NAME}/actions/runs").respond(
        json={
            "workflow_runs": [
                run_payload(id=1, name="CI"),
                run_payload(id=2, name="Lint"),
                run_payload(id=3, name="Release"),
            ]
        }
    )

    response = sync(client, repository)

    assert response.json() == {"runs_seen": 3, "runs_added": 3, "deployments_added": 1}
    assert db.scalar(select(Deployment)).commit_sha == "a" * 40


def test_a_deployment_off_the_default_branch_is_not_production(
    client: TestClient, db: Session, signed_in: User, repository: Repository, actions
):
    actions.get(f"{API_URL}/repos/{FULL_NAME}/actions/runs").respond(
        json={"workflow_runs": [run_payload(head_branch="staging")]}
    )

    sync(client, repository)

    assert db.scalar(select(Deployment)).environment == "staging"


def test_sync_refuses_a_repository_owned_by_someone_else(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    stranger = User(github_id=777, username="stranger", access_token_encrypted="x")
    db.add(stranger)
    db.flush()
    db.execute(
        Repository.__table__.update()
        .where(Repository.id == repository.id)
        .values(user_id=stranger.id)
    )

    assert sync(client, repository).status_code == 404


def test_sync_reports_a_revoked_token(
    client: TestClient, signed_in: User, repository: Repository, actions
):
    actions.get(f"{API_URL}/repos/{FULL_NAME}/actions/runs").respond(
        401, json={"message": "Bad credentials"}
    )

    assert sync(client, repository).status_code == 401
