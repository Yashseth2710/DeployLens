from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.health import HealthCheck, HealthResult
from app.models.repository import Repository
from app.models.user import User
from app.services import probes

TARGET = "https://deploylens.example.com/health"


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


@pytest.fixture
def check(db: Session, repository: Repository) -> HealthCheck:
    record = HealthCheck(repository_id=repository.id, url=TARGET)
    db.add(record)
    db.flush()
    return record


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Resolution is checked at probe time, and example.com does not resolve to
    anything useful from a test runner."""
    monkeypatch.setattr(probes, "resolves_publicly", lambda host: True)


def trigger(client: TestClient, secret: str | None = None):
    token = get_settings().cron_secret if secret is None else secret
    return client.post("/api/cron/health-check", headers={"Authorization": f"Bearer {token}"})


def record_result(db: Session, check: HealthCheck, *, minutes_ago: int, status: str = "up"):
    result = HealthResult(
        health_check_id=check.id,
        status=status,
        checked_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    db.add(result)
    db.flush()
    return result


@respx.mock
def test_a_reachable_endpoint_is_recorded_as_up(
    client: TestClient, db: Session, check: HealthCheck
):
    respx.get(TARGET).respond(200)

    response = trigger(client)

    assert response.json() == {"checked": 1, "up": 1, "down": 0, "pruned": 0}
    result = db.scalar(select(HealthResult))
    assert result.status == "up"
    assert result.status_code == 200
    assert result.response_time_ms is not None
    assert result.error_message is None


@respx.mock
def test_an_unexpected_status_is_down_and_says_so(
    client: TestClient, db: Session, check: HealthCheck
):
    respx.get(TARGET).respond(503)

    assert trigger(client).json()["down"] == 1
    result = db.scalar(select(HealthResult))
    assert result.status == "down"
    assert result.status_code == 503
    assert result.error_message == "Expected 200, got 503"


@respx.mock
def test_a_timeout_is_down_without_a_status_code(
    client: TestClient, db: Session, check: HealthCheck
):
    respx.get(TARGET).mock(side_effect=httpx.ConnectTimeout("too slow"))

    assert trigger(client).json()["down"] == 1
    result = db.scalar(select(HealthResult))
    assert result.status == "down"
    assert result.status_code is None
    assert result.error_message == "ConnectTimeout"


@respx.mock
def test_a_check_expecting_something_other_than_200_is_honoured(
    client: TestClient, db: Session, check: HealthCheck
):
    check.expected_status = 204
    db.flush()
    respx.get(TARGET).respond(204)

    assert trigger(client).json()["up"] == 1


@respx.mock
def test_a_check_probed_recently_is_not_probed_again(
    client: TestClient, db: Session, check: HealthCheck
):
    record_result(db, check, minutes_ago=10)
    probed = respx.get(TARGET).respond(200)

    assert trigger(client).json()["checked"] == 0
    assert not probed.called


@respx.mock
def test_a_check_overdue_by_its_own_interval_is_probed(
    client: TestClient, db: Session, check: HealthCheck
):
    record_result(db, check, minutes_ago=90)
    respx.get(TARGET).respond(200)

    assert trigger(client).json()["checked"] == 1


@respx.mock
def test_a_slower_interval_is_not_dragged_to_the_schedule_cadence(
    client: TestClient, db: Session, check: HealthCheck
):
    check.interval_minutes = 720
    db.flush()
    record_result(db, check, minutes_ago=90)
    probed = respx.get(TARGET).respond(200)

    assert trigger(client).json()["checked"] == 0
    assert not probed.called


@respx.mock
def test_a_paused_check_is_left_alone(client: TestClient, db: Session, check: HealthCheck):
    check.enabled = False
    db.flush()
    probed = respx.get(TARGET).respond(200)

    assert trigger(client).json()["checked"] == 0
    assert not probed.called


@respx.mock
def test_a_host_that_stops_resolving_publicly_is_down_and_never_requested(
    client: TestClient, db: Session, check: HealthCheck, monkeypatch
):
    monkeypatch.setattr(probes, "resolves_publicly", lambda host: False)
    probed = respx.get(TARGET).respond(200)

    assert trigger(client).json()["down"] == 1
    assert not probed.called
    assert db.scalar(select(HealthResult)).error_message.startswith("Host does not resolve")


@respx.mock
def test_results_older_than_the_retention_window_are_swept(
    client: TestClient, db: Session, check: HealthCheck
):
    old = HealthResult(
        health_check_id=check.id,
        status="up",
        checked_at=datetime.now(UTC) - timedelta(days=probes.RESULT_RETENTION_DAYS + 1),
    )
    db.add(old)
    db.flush()
    respx.get(TARGET).respond(200)

    assert trigger(client).json()["pruned"] == 1
    remaining = db.scalars(select(HealthResult)).all()
    assert len(remaining) == 1
    assert remaining[0].id != old.id


def test_the_runner_refuses_a_wrong_or_missing_secret(client: TestClient, check: HealthCheck):
    assert trigger(client, secret="not-the-secret").status_code == 401
    assert client.post("/api/cron/health-check").status_code == 401


@respx.mock
def test_probe_history_is_readable_by_the_owner_only(
    client: TestClient, db: Session, signed_in: User, check: HealthCheck
):
    respx.get(TARGET).respond(200)
    trigger(client)

    results = client.get(f"/api/health-checks/{check.id}/results").json()
    assert len(results) == 1
    assert results[0]["status"] == "up"

    stranger = User(github_id=777, username="stranger", access_token_encrypted="x")
    db.add(stranger)
    db.flush()
    db.execute(
        Repository.__table__.update()
        .where(Repository.id == check.repository_id)
        .values(user_id=stranger.id)
    )

    assert client.get(f"/api/health-checks/{check.id}/results").status_code == 404
