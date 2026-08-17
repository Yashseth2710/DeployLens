from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.health import HealthCheck, HealthResult
from app.models.repository import Repository
from app.models.user import User
from app.models.workflow import Deployment
from app.services import metrics
from app.services.metrics import DeliveryMetrics, UptimeMetrics

NOW = datetime.now(UTC)


@pytest.fixture
def repository(db: Session, user: User) -> Repository:
    return add_repository(db, user, "octocat/deploylens", 900001)


def add_repository(db: Session, owner: User, full_name: str, github_repo_id: int) -> Repository:
    record = Repository(
        user_id=owner.id,
        github_repo_id=github_repo_id,
        name=full_name.split("/")[1],
        full_name=full_name,
        owner=full_name.split("/")[0],
        default_branch="main",
        github_url=f"https://github.com/{full_name}",
    )
    db.add(record)
    db.flush()
    return record


def add_deployment(
    db: Session, repository: Repository, *, status: str, days_ago: float = 0, duration: int = 120
) -> Deployment:
    record = Deployment(
        repository_id=repository.id,
        environment="production",
        status=status,
        branch="main",
        started_at=NOW - timedelta(days=days_ago),
        completed_at=NOW - timedelta(days=days_ago) + timedelta(seconds=duration),
        duration_seconds=duration,
    )
    db.add(record)
    db.flush()
    return record


def add_probe(db: Session, check: HealthCheck, *, status: str, days_ago: float = 0, ms: int = 200):
    db.add(
        HealthResult(
            health_check_id=check.id,
            status=status,
            status_code=200 if status == "up" else 503,
            response_time_ms=ms,
            checked_at=NOW - timedelta(days=days_ago),
        )
    )
    db.flush()


@pytest.fixture
def check(db: Session, repository: Repository) -> HealthCheck:
    record = HealthCheck(repository_id=repository.id, url="https://deploylens.example.com/health")
    db.add(record)
    db.flush()
    return record


def test_success_rate_counts_only_decided_outcomes(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    add_deployment(db, repository, status="success")
    add_deployment(db, repository, status="success")
    add_deployment(db, repository, status="failure")
    add_deployment(db, repository, status="cancelled")

    delivery = client.get("/api/analytics/overview").json()["delivery"]

    assert delivery["deployments"] == 4
    assert delivery["succeeded"] == 2
    assert delivery["failed"] == 1
    # Two of three decided runs succeeded; the cancelled one says nothing either way.
    assert delivery["success_rate"] == 66.7


def test_deployments_outside_the_window_are_left_out(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    add_deployment(db, repository, status="success", days_ago=2)
    add_deployment(db, repository, status="failure", days_ago=45)

    delivery = client.get("/api/analytics/overview", params={"days": 7}).json()["delivery"]

    assert delivery["deployments"] == 1
    assert delivery["success_rate"] == 100.0


def test_frequency_and_duration_are_reported(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for day in range(6):
        add_deployment(db, repository, status="success", days_ago=day, duration=60 * (day + 1))

    delivery = client.get("/api/analytics/overview", params={"days": 7}).json()["delivery"]

    assert delivery["deployments_per_week"] == 6.0
    assert delivery["average_duration_seconds"] == 210
    assert delivery["last_deployment_at"] is not None


def test_uptime_is_the_share_of_probes_that_answered(
    client: TestClient, db: Session, signed_in: User, check: HealthCheck
):
    for _ in range(9):
        add_probe(db, check, status="up")
    add_probe(db, check, status="down", ms=800)

    uptime = client.get("/api/analytics/overview").json()["uptime"]

    assert uptime["probes"] == 10
    assert uptime["up"] == 9
    assert uptime["uptime_percent"] == 90.0
    assert uptime["monitored_urls"] == 1
    assert uptime["average_response_time_ms"] == 260


def test_a_project_with_no_health_check_is_not_scored_as_if_it_were_down(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    for day in range(3):
        add_deployment(db, repository, status="success", days_ago=day)

    body = client.get("/api/analytics/overview", params={"days": 7}).json()

    assert body["uptime"]["uptime_percent"] is None
    # Success and frequency both full marks, and uptime is dropped rather than zeroed.
    assert body["health_score"] == 100


def test_the_score_blends_delivery_and_uptime(
    client: TestClient, db: Session, signed_in: User, repository: Repository, check: HealthCheck
):
    add_deployment(db, repository, status="success")
    add_deployment(db, repository, status="failure")
    for _ in range(8):
        add_probe(db, check, status="up")
    for _ in range(2):
        add_probe(db, check, status="down")

    body = client.get("/api/analytics/overview", params={"days": 7}).json()

    # 50% success, 80% uptime, 2 deploys a week against a target of 3:
    # 0.5(50) + 0.3(80) + 0.2(66.7) = 62.3
    assert body["health_score"] == 62


def test_a_repository_with_nothing_recorded_has_no_score(
    client: TestClient, signed_in: User, repository: Repository
):
    body = client.get("/api/analytics/overview").json()

    assert body["health_score"] is None
    assert body["repositories"][0]["health_score"] is None
    assert body["delivery"]["deployments"] == 0


def test_each_repository_is_scored_on_its_own(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    other = add_repository(db, signed_in, "octocat/notes", 900002)
    add_deployment(db, repository, status="success")
    add_deployment(db, other, status="failure")

    cards = client.get("/api/analytics/overview").json()["repositories"]

    by_name = {card["full_name"]: card for card in cards}
    assert by_name["octocat/deploylens"]["delivery"]["success_rate"] == 100.0
    assert by_name["octocat/notes"]["delivery"]["success_rate"] == 0.0


def test_trends_group_by_day(
    client: TestClient, db: Session, signed_in: User, repository: Repository, check: HealthCheck
):
    add_deployment(db, repository, status="success", days_ago=1)
    add_deployment(db, repository, status="failure", days_ago=1)
    add_deployment(db, repository, status="success", days_ago=0)
    add_probe(db, check, status="up", days_ago=1)
    add_probe(db, check, status="down", days_ago=1)

    body = client.get("/api/analytics/trends", params={"days": 7}).json()

    assert len(body["deployments"]) == 2
    yesterday = body["deployments"][0]
    assert yesterday["deployments"] == 2
    assert yesterday["succeeded"] == 1
    assert yesterday["failed"] == 1
    assert body["uptime"][0]["uptime_percent"] == 50.0


def test_trends_can_be_narrowed_to_one_repository(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    other = add_repository(db, signed_in, "octocat/notes", 900002)
    add_deployment(db, repository, status="success")
    add_deployment(db, other, status="success")

    body = client.get("/api/analytics/trends", params={"repository_id": str(repository.id)}).json()

    assert sum(point["deployments"] for point in body["deployments"]) == 1


def test_another_users_data_is_never_counted(
    client: TestClient, db: Session, signed_in: User, repository: Repository
):
    stranger = User(github_id=777, username="stranger", access_token_encrypted="x")
    db.add(stranger)
    db.flush()
    theirs = add_repository(db, stranger, "stranger/secret", 900003)
    add_deployment(db, theirs, status="success")

    body = client.get("/api/analytics/overview").json()

    assert body["connected_repositories"] == 1
    assert body["delivery"]["deployments"] == 0
    assert (
        client.get("/api/analytics/trends", params={"repository_id": str(theirs.id)}).status_code
        == 404
    )


def test_the_window_is_bounded(client: TestClient, signed_in: User):
    assert client.get("/api/analytics/overview", params={"days": 0}).status_code == 422
    assert client.get("/api/analytics/overview", params={"days": 400}).status_code == 422


def test_analytics_need_a_session(client: TestClient):
    assert client.get("/api/analytics/overview").status_code == 401
    assert client.get("/api/analytics/trends").status_code == 401


def test_the_score_renormalises_when_a_component_is_missing():
    delivery = DeliveryMetrics(
        deployments=3,
        succeeded=3,
        failed=0,
        success_rate=100.0,
        average_duration_seconds=60,
        deployments_per_week=3.0,
        last_deployment_at=NOW,
    )
    no_probes = UptimeMetrics(0, 0, 0, None, None)
    half_up = UptimeMetrics(1, 10, 5, 50.0, 200)

    assert metrics.health_score(delivery, no_probes) == 100
    assert metrics.health_score(delivery, half_up) == 85
