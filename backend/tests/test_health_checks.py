from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.health import HealthCheck
from app.models.repository import Repository
from app.models.user import User
from app.services import probes

URL = "https://deploylens.example.com/health"


@pytest.fixture(autouse=True)
def probed(monkeypatch: pytest.MonkeyPatch) -> list[UUID]:
    """Creating a check schedules a probe, which would otherwise reach the network
    from every test in this file. Recording the call is also what the tests assert."""
    asked: list[UUID] = []
    monkeypatch.setattr(probes, "probe_once", asked.append, raising=True)
    return asked


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


def create(client: TestClient, repository: Repository, **overrides):
    body = {"repository_id": str(repository.id), "url": URL} | overrides
    return client.post("/api/health-checks", json=body)


def _checks(db: Session, repository: Repository) -> list[HealthCheck]:
    """Scoped to this test's own repository. The suite runs against a database a
    developer is also monitoring with, so a bare select reads their endpoints."""
    return list(db.scalars(select(HealthCheck).where(HealthCheck.repository_id == repository.id)))


def test_a_check_starts_hourly_enabled_and_expecting_200(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    response = create(client, repository)

    assert response.status_code == 201
    body = response.json()
    assert body["url"] == URL
    assert body["interval_minutes"] == 60
    assert body["expected_status"] == 200
    assert body["enabled"] is True
    assert _checks(db, repository) != []


def test_the_same_url_is_not_checked_twice_for_one_repository(
    client: TestClient, signed_in: User, repository: Repository
):
    create(client, repository)

    assert create(client, repository).status_code == 409


def test_a_repository_cannot_collect_unlimited_checks(
    client: TestClient, signed_in: User, repository: Repository
):
    for index in range(3):
        assert create(client, repository, url=f"{URL}/{index}").status_code == 201

    response = create(client, repository, url=f"{URL}/spare")

    assert response.status_code == 409
    assert "at most 3" in response.json()["detail"]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/health",
        "http://127.0.0.1/health",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/health",
        "http://192.168.1.10/health",
        "http://metadata.google.internal/",
        "http://db.internal/health",
        "file:///etc/passwd",
        "not a url",
    ],
)
def test_a_url_the_internet_cannot_reach_is_refused(
    client: TestClient, signed_in: User, repository: Repository, url: str
):
    assert create(client, repository, url=url).status_code == 422


def test_the_probe_interval_has_a_floor_and_a_ceiling(
    client: TestClient, signed_in: User, repository: Repository
):
    assert create(client, repository, interval_minutes=5).status_code == 422
    assert create(client, repository, interval_minutes=10080).status_code == 422
    assert create(client, repository, interval_minutes=360).status_code == 201


def test_a_check_can_be_retargeted_and_paused(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    check_id = create(client, repository).json()["id"]

    response = client.patch(
        f"/api/health-checks/{check_id}",
        json={"url": f"{URL}/v2", "enabled": False, "expected_status": 204},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == f"{URL}/v2"
    assert body["enabled"] is False
    assert body["expected_status"] == 204
    assert body["interval_minutes"] == 60


def test_a_new_endpoint_is_read_without_waiting_for_the_schedule(
    client: TestClient, signed_in: User, repository: Repository, probed: list[UUID]
):
    """The runner fires hourly, so an endpoint added now would read as unmeasured for
    an hour — which is indistinguishable from the URL having been rejected."""
    check_id = create(client, repository).json()["id"]

    assert [str(asked) for asked in probed] == [check_id]


def test_a_corrected_url_is_read_but_a_changed_interval_is_not(
    client: TestClient, signed_in: User, repository: Repository, probed: list[UUID]
):
    """A typo fixed here should clear the failure it caused, rather than leaving the
    old address's result standing for another hour. Retiming is not a new target."""
    check_id = create(client, repository).json()["id"]
    probed.clear()

    client.patch(f"/api/health-checks/{check_id}", json={"interval_minutes": 120})
    assert probed == []

    client.patch(f"/api/health-checks/{check_id}", json={"url": f"{URL}/v2"})
    assert [str(asked) for asked in probed] == [check_id]


def test_an_update_cannot_collide_with_another_url_on_the_same_repository(
    client: TestClient, signed_in: User, repository: Repository
):
    first = create(client, repository).json()["id"]
    create(client, repository, url=f"{URL}/v2")

    response = client.patch(f"/api/health-checks/{first}", json={"url": f"{URL}/v2"})

    assert response.status_code == 409


def test_checks_are_listed_and_can_be_narrowed_to_one_repository(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    create(client, repository)
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
    create(client, other, url="https://notes.example.com/health")

    assert len(client.get("/api/health-checks").json()) == 2
    narrowed = client.get("/api/health-checks", params={"repository_id": str(repository.id)}).json()
    assert [item["url"] for item in narrowed] == [URL]


def test_deleting_a_check_removes_it(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    check_id = create(client, repository).json()["id"]

    assert client.delete(f"/api/health-checks/{check_id}").status_code == 204
    assert _checks(db, repository) == []


def test_checks_on_another_users_repository_are_out_of_reach(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    check_id = create(client, repository).json()["id"]
    stranger = User(github_id=777, username="stranger", access_token_encrypted="x")
    db.add(stranger)
    db.flush()
    db.execute(
        Repository.__table__.update()
        .where(Repository.id == repository.id)
        .values(user_id=stranger.id)
    )

    paused = client.patch(f"/api/health-checks/{check_id}", json={"enabled": False})

    assert client.get("/api/health-checks").json() == []
    assert paused.status_code == 404
    assert client.delete(f"/api/health-checks/{check_id}").status_code == 404
    assert create(client, repository, url=f"{URL}/new").status_code == 404


def test_health_check_endpoints_need_a_session(client: TestClient):
    assert client.get("/api/health-checks").status_code == 401
    assert client.post("/api/health-checks", json={}).status_code == 401
