from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.user import User
from app.models.workflow import Deployment, WorkflowRun

STARTED = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


@pytest.fixture
def repository(db: Session, user: User) -> Repository:
    record = Repository(
        user_id=user.id,
        github_repo_id=900001,
        name="deploylens",
        full_name="octocat/deploylens",
        owner="octocat",
        default_branch="main",
        github_url="https://github.com/octocat/deploylens",
    )
    db.add(record)
    db.flush()
    return record


def add_deployment(db: Session, repository: Repository, *, minutes: int, status: str):
    run = WorkflowRun(
        repository_id=repository.id,
        github_run_id=1000 + minutes,
        workflow_name="Deploy to production",
        branch="main",
        commit_sha="b" * 40,
        status="completed",
        conclusion=status,
        started_at=STARTED + timedelta(minutes=minutes),
    )
    db.add(run)
    db.flush()
    deployment = Deployment(
        repository_id=repository.id,
        workflow_run_id=run.id,
        environment="production",
        status=status,
        branch="main",
        commit_sha="b" * 40,
        author="octocat",
        started_at=STARTED + timedelta(minutes=minutes),
    )
    db.add(deployment)
    db.flush()
    return deployment


def test_deployments_are_listed_newest_first_with_their_repository(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    add_deployment(db, repository, minutes=0, status="success")
    add_deployment(db, repository, minutes=30, status="failure")

    listed = client.get("/api/deployments").json()

    assert [item["status"] for item in listed] == ["failure", "success"]
    assert listed[0]["repository_full_name"] == "octocat/deploylens"


def test_deployments_can_be_narrowed_to_one_repository(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    add_deployment(db, repository, minutes=0, status="success")
    other = Repository(
        user_id=signed_in.id,
        github_repo_id=900002,
        name="notes",
        full_name="octocat/notes",
        owner="octocat",
        default_branch="main",
        github_url="https://github.com/octocat/notes",
    )
    db.add(other)
    db.flush()
    add_deployment(db, other, minutes=10, status="success")

    listed = client.get("/api/deployments", params={"repository_id": str(repository.id)}).json()

    assert len(listed) == 1
    assert listed[0]["repository_full_name"] == "octocat/deploylens"


def test_deployment_paging_is_bounded(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for minute in range(3):
        add_deployment(db, repository, minutes=minute, status="success")

    page = client.get("/api/deployments", params={"limit": 2, "offset": 2}).json()

    assert len(page) == 1
    assert client.get("/api/deployments", params={"limit": 0}).status_code == 422


def test_deployment_detail_carries_the_workflow_run(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    deployment = add_deployment(db, repository, minutes=0, status="failure")

    detail = client.get(f"/api/deployments/{deployment.id}").json()

    assert detail["status"] == "failure"
    assert detail["workflow_run"]["workflow_name"] == "Deploy to production"
    assert detail["workflow_run"]["conclusion"] == "failure"


def test_another_users_deployment_is_not_readable(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    deployment = add_deployment(db, repository, minutes=0, status="success")
    stranger = User(github_id=777, username="stranger", access_token_encrypted="x")
    db.add(stranger)
    db.flush()
    db.execute(
        Repository.__table__.update()
        .where(Repository.id == repository.id)
        .values(user_id=stranger.id)
    )

    assert client.get(f"/api/deployments/{deployment.id}").status_code == 404
    assert client.get("/api/deployments").json() == []


def test_deployment_endpoints_need_a_session(client: TestClient):
    assert client.get("/api/deployments").status_code == 401
