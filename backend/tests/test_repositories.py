import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.user import User
from app.services.github_api import API_URL

DASHBOARD = {
    "id": 900001,
    "name": "deploylens",
    "full_name": "octocat/deploylens",
    "owner": {"login": "octocat"},
    "default_branch": "main",
    "html_url": "https://github.com/octocat/deploylens",
    "private": False,
    "pushed_at": "2026-08-14T09:30:00Z",
}
NOTES = {
    "id": 900002,
    "name": "notes",
    "full_name": "octocat/notes",
    "owner": {"login": "octocat"},
    "default_branch": "trunk",
    "html_url": "https://github.com/octocat/notes",
    "private": True,
    "pushed_at": None,
}


@pytest.fixture
def github():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{API_URL}/user/repos").respond(json=[DASHBOARD, NOTES])
        mock.get(f"{API_URL}/repositories/{DASHBOARD['id']}").respond(json=DASHBOARD)
        mock.get(f"{API_URL}/repositories/{NOTES['id']}").respond(json=NOTES)
        yield mock


def connect(client: TestClient, github_repo_id: int):
    return client.post("/api/repositories", json={"github_repo_id": github_repo_id})


def test_connecting_stores_the_repository_as_github_describes_it(
    client: TestClient, db: Session, signed_in: User, github
):
    response = connect(client, DASHBOARD["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "octocat/deploylens"
    assert body["default_branch"] == "main"

    stored = db.scalar(select(Repository).where(Repository.user_id == signed_in.id))
    assert stored is not None
    assert stored.github_repo_id == DASHBOARD["id"]
    assert stored.owner == "octocat"


def test_connecting_the_same_repository_twice_is_rejected(
    client: TestClient, signed_in: User, github
):
    connect(client, DASHBOARD["id"])

    assert connect(client, DASHBOARD["id"]).status_code == 409


def test_connecting_a_repository_the_token_cannot_see_is_refused(
    client: TestClient, db: Session, signed_in: User, github
):
    github.get(f"{API_URL}/repositories/424242").respond(404, json={"message": "Not Found"})

    response = connect(client, 424242)

    assert response.status_code == 404
    assert db.scalar(select(Repository)) is None


def test_available_marks_the_repositories_already_connected(
    client: TestClient, signed_in: User, github
):
    connect(client, DASHBOARD["id"])

    available = client.get("/api/repositories/available").json()

    assert [repository["full_name"] for repository in available] == [
        "octocat/deploylens",
        "octocat/notes",
    ]
    assert [repository["connected"] for repository in available] == [True, False]
    assert available[1]["private"] is True
    assert available[1]["pushed_at"] is None


def test_available_reports_a_revoked_grant_as_a_sign_in_problem(
    client: TestClient, signed_in: User, github
):
    github.get(f"{API_URL}/user/repos").respond(401, json={"message": "Bad credentials"})

    assert client.get("/api/repositories/available").status_code == 401


def test_available_passes_a_spent_rate_limit_through(client: TestClient, signed_in: User, github):
    github.get(f"{API_URL}/user/repos").respond(
        403, json={"message": "API rate limit exceeded"}, headers={"x-ratelimit-remaining": "0"}
    )

    assert client.get("/api/repositories/available").status_code == 429


def test_connected_repositories_are_listed_newest_first(
    client: TestClient, signed_in: User, github
):
    connect(client, DASHBOARD["id"])
    connect(client, NOTES["id"])

    listed = client.get("/api/repositories").json()

    assert [repository["name"] for repository in listed] == ["notes", "deploylens"]


def test_disconnecting_removes_the_repository(
    client: TestClient, db: Session, signed_in: User, github
):
    repository_id = connect(client, DASHBOARD["id"]).json()["id"]

    assert client.delete(f"/api/repositories/{repository_id}").status_code == 204
    assert db.scalar(select(Repository)) is None


def test_one_user_cannot_disconnect_another_users_repository(
    client: TestClient, db: Session, signed_in: User, github
):
    repository_id = connect(client, DASHBOARD["id"]).json()["id"]
    stranger = User(github_id=777, username="stranger", access_token_encrypted="x")
    db.add(stranger)
    db.flush()
    db.execute(
        Repository.__table__.update()
        .where(Repository.id == repository_id)
        .values(user_id=stranger.id)
    )

    assert client.delete(f"/api/repositories/{repository_id}").status_code == 404


def test_disconnecting_something_that_is_not_connected_is_a_404(
    client: TestClient, signed_in: User
):
    unknown = "0199b5b8-0000-7000-8000-000000000000"

    assert client.delete(f"/api/repositories/{unknown}").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/repositories"),
        ("get", "/api/repositories/available"),
        ("post", "/api/repositories"),
    ],
)
def test_every_repository_endpoint_needs_a_session(client: TestClient, method: str, path: str):
    assert getattr(client, method)(path).status_code == 401
