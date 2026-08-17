import hashlib
import hmac
import json

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.repository import Repository
from app.models.user import User
from app.models.webhook import WebhookEvent
from app.models.workflow import Deployment, WorkflowRun
from app.services import webhooks
from app.services.github_api import API_URL

GITHUB_REPO_ID = 900001


@pytest.fixture
def repository(db: Session, user: User) -> Repository:
    record = Repository(
        user_id=user.id,
        github_repo_id=GITHUB_REPO_ID,
        name="deploylens",
        full_name="octocat/deploylens",
        owner="octocat",
        default_branch="main",
        github_url="https://github.com/octocat/deploylens",
    )
    db.add(record)
    db.flush()
    return record


def workflow_run_event(**overrides):
    return {
        "action": "completed",
        "repository": {"id": GITHUB_REPO_ID, "full_name": "octocat/deploylens"},
        "workflow_run": {
            "id": 77001,
            "name": "Deploy to production",
            "head_branch": "main",
            "head_sha": "c" * 40,
            "status": "completed",
            "conclusion": "success",
            "event": "push",
            "actor": {"login": "octocat"},
            "run_started_at": "2026-08-16T12:00:00Z",
            "updated_at": "2026-08-16T12:03:00Z",
            "html_url": "https://github.com/octocat/deploylens/actions/runs/77001",
        }
        | overrides,
    }


def deliver(client: TestClient, payload: dict, *, delivery: str, event: str = "workflow_run"):
    body = json.dumps(payload).encode()
    secret = get_settings().github_webhook_secret.encode()
    signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery,
            "X-GitHub-Event": event,
            "Content-Type": "application/json",
        },
    )


def test_a_completed_run_arrives_as_a_deployment(
    client: TestClient, db: Session, repository: Repository
):
    response = deliver(client, workflow_run_event(), delivery="d-1")

    assert response.status_code == 202
    assert response.json() == {"result": "recorded"}

    run = db.scalar(select(WorkflowRun).where(WorkflowRun.github_run_id == 77001))
    assert run is not None
    assert run.duration_seconds == 180

    deployment = db.scalar(select(Deployment).where(Deployment.workflow_run_id == run.id))
    assert deployment is not None
    assert deployment.status == "success"
    assert deployment.environment == "production"


def test_a_redelivered_event_changes_nothing(
    client: TestClient, db: Session, repository: Repository
):
    deliver(client, workflow_run_event(), delivery="d-2")

    repeat = deliver(client, workflow_run_event(conclusion="failure"), delivery="d-2")

    assert repeat.json() == {"result": "duplicate"}
    assert db.scalar(select(WorkflowRun)).conclusion == "success"
    assert len(db.scalars(select(WebhookEvent)).all()) == 1


def test_a_later_delivery_for_the_same_run_updates_it(
    client: TestClient, db: Session, repository: Repository
):
    deliver(client, workflow_run_event(status="in_progress", conclusion=None), delivery="d-3")

    deliver(client, workflow_run_event(), delivery="d-4")

    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.repository_id == repository.id)).all()
    assert len(runs) == 1
    assert runs[0].conclusion == "success"
    assert runs[0].duration_seconds == 180


def test_the_raw_payload_is_kept_for_replay(
    client: TestClient, db: Session, repository: Repository
):
    deliver(client, workflow_run_event(), delivery="d-5")

    event = db.scalar(select(WebhookEvent))
    assert event.github_delivery_id == "d-5"
    assert event.event_type == "workflow_run"
    assert event.repository_id == repository.id
    assert event.payload["workflow_run"]["id"] == 77001
    assert event.processed is True


def test_a_forged_signature_is_refused(client: TestClient, db: Session, repository: Repository):
    response = client.post(
        "/api/webhooks/github",
        content=json.dumps(workflow_run_event()).encode(),
        headers={
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
            "X-GitHub-Delivery": "d-6",
            "X-GitHub-Event": "workflow_run",
        },
    )

    assert response.status_code == 401
    assert db.scalar(select(WebhookEvent)) is None


def test_an_unsigned_delivery_is_refused(client: TestClient, repository: Repository):
    response = client.post(
        "/api/webhooks/github",
        content=json.dumps(workflow_run_event()).encode(),
        headers={"X-GitHub-Delivery": "d-7", "X-GitHub-Event": "workflow_run"},
    )

    assert response.status_code == 401


def test_a_tampered_body_no_longer_matches_its_signature(
    client: TestClient, db: Session, repository: Repository
):
    body = json.dumps(workflow_run_event()).encode()
    secret = get_settings().github_webhook_secret.encode()
    signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

    response = client.post(
        "/api/webhooks/github",
        content=json.dumps(workflow_run_event(conclusion="failure")).encode(),
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": "d-8",
            "X-GitHub-Event": "workflow_run",
        },
    )

    assert response.status_code == 401
    assert db.scalar(select(WorkflowRun).where(WorkflowRun.repository_id == repository.id)) is None


def test_a_ping_is_answered_without_being_stored(client: TestClient, db: Session):
    response = deliver(client, {"zen": "Design for failure."}, delivery="d-9", event="ping")

    assert response.json() == {"result": "pong"}
    assert db.scalar(select(WebhookEvent)) is None


def test_an_event_we_do_not_act_on_is_still_kept(
    client: TestClient, db: Session, repository: Repository
):
    response = deliver(client, workflow_run_event(), delivery="d-10", event="push")

    assert response.json() == {"result": "ignored"}
    event = db.scalar(select(WebhookEvent).where(WebhookEvent.github_delivery_id == "d-10"))
    assert event.event_type == "push"
    assert event.processed is False
    assert db.scalar(select(WorkflowRun).where(WorkflowRun.repository_id == repository.id)) is None


def test_a_delivery_for_a_repository_nobody_connected_is_kept_but_not_applied(
    client: TestClient, db: Session
):
    payload = workflow_run_event()
    payload["repository"]["id"] = 123456

    response = deliver(client, payload, delivery="d-11")

    assert response.json() == {"result": "unknown_repository"}
    event = db.scalar(select(WebhookEvent).where(WebhookEvent.github_delivery_id == "d-11"))
    assert event.repository_id is None
    assert db.scalar(select(WorkflowRun).where(WorkflowRun.github_run_id == 77001)) is None


def test_a_delivery_without_its_headers_is_rejected(client: TestClient):
    body = json.dumps(workflow_run_event()).encode()
    secret = get_settings().github_webhook_secret.encode()
    signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

    response = client.post(
        "/api/webhooks/github", content=body, headers={"X-Hub-Signature-256": signature}
    )

    assert response.status_code == 400


def test_a_body_that_is_not_json_is_rejected(client: TestClient):
    body = b"not json at all"
    secret = get_settings().github_webhook_secret.encode()
    signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

    response = client.post(
        "/api/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": "d-12",
            "X-GitHub-Event": "workflow_run",
        },
    )

    assert response.status_code == 400


@pytest.fixture
def production(monkeypatch):
    """Registration is skipped unless the app has a public URL, which localhost is not."""
    monkeypatch.setattr(get_settings(), "app_url", "https://deploylens.example.com")
    return "https://deploylens.example.com/api/webhooks/github"


def test_connecting_registers_a_hook_for_workflow_runs(repository: Repository, production: str):
    hooks = f"{API_URL}/repos/{repository.full_name}/hooks"
    with respx.mock as mock:
        mock.get(hooks).respond(json=[])
        created = mock.post(hooks).respond(201, json={"id": 1})

        webhooks.register("gho_live", repository)

    assert created.called
    body = json.loads(created.calls[0].request.content)
    assert body["events"] == ["workflow_run"]
    assert body["config"]["url"] == production
    assert body["config"]["secret"] == get_settings().github_webhook_secret


def test_a_repository_that_already_has_the_hook_does_not_get_a_second(
    repository: Repository, production: str
):
    hooks = f"{API_URL}/repos/{repository.full_name}/hooks"
    with respx.mock as mock:
        mock.get(hooks).respond(json=[{"id": 9, "config": {"url": production}}])
        created = mock.post(hooks).respond(201, json={"id": 10})

        webhooks.register("gho_live", repository)

    assert not created.called


def test_disconnecting_removes_the_hook_it_created(repository: Repository, production: str):
    hooks = f"{API_URL}/repos/{repository.full_name}/hooks"
    with respx.mock as mock:
        mock.get(hooks).respond(json=[{"id": 9, "config": {"url": production}}])
        removed = mock.delete(f"{hooks}/9").respond(204)

        webhooks.unregister("gho_live", repository)

    assert removed.called


def test_no_hook_is_registered_against_a_local_url(repository: Repository):
    with respx.mock as mock:
        listed = mock.get(f"{API_URL}/repos/{repository.full_name}/hooks").respond(json=[])

        webhooks.register("gho_live", repository)

    assert not listed.called
