import hashlib
import hmac
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.repository import Repository
from app.models.webhook import WebhookEvent
from app.services import github_api, workflow_sync

SIGNATURE_HEADER = "X-Hub-Signature-256"
DELIVERY_HEADER = "X-GitHub-Delivery"
EVENT_HEADER = "X-GitHub-Event"

HANDLED_EVENT = "workflow_run"


def callback_url() -> str:
    return f"{get_settings().app_url}/api/webhooks/github"


def signature_matches(body: bytes, signature: str | None) -> bool:
    """An unset secret rejects everything. A deployment that forgot to configure one
    should look broken rather than accept whatever arrives."""
    secret = get_settings().github_webhook_secret
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def register(access_token: str, repository: Repository) -> None:
    """GitHub will not deliver to localhost, so development connects without a hook and
    relies on manual syncing instead."""
    settings = get_settings()
    if not settings.app_url.startswith("https://"):
        return
    github_api.create_webhook(
        access_token, repository.full_name, callback_url(), settings.github_webhook_secret
    )


def unregister(access_token: str, repository: Repository) -> None:
    if not get_settings().app_url.startswith("https://"):
        return
    github_api.delete_webhook(access_token, repository.full_name, callback_url())


def record_delivery(db: Session, delivery_id: str, event_type: str, payload: dict[str, Any]) -> str:
    """Returns what happened to the delivery, which is what the response body carries.

    The event row is written before anything is interpreted: the unique delivery id is
    what makes a GitHub retry a no-op, and the stored payload is what lets a parsing
    bug be replayed rather than guessed at.
    """
    repositories = _repositories_for(db, payload)
    event_id = db.scalar(
        insert(WebhookEvent)
        .values(
            github_delivery_id=delivery_id,
            event_type=event_type,
            repository_id=repositories[0].id if repositories else None,
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=["github_delivery_id"])
        .returning(WebhookEvent.id)
    )
    if event_id is None:
        db.commit()
        return "duplicate"

    if event_type != HANDLED_EVENT:
        db.commit()
        return "ignored"

    _apply_workflow_run(db, repositories, payload)
    _mark_processed(db, event_id)
    return "recorded" if repositories else "unknown_repository"


def _repositories_for(db: Session, payload: dict[str, Any]) -> list[Repository]:
    """One GitHub repository can be connected by several accounts, and each of them
    keeps its own copy of the history, so every match is updated."""
    github_repo_id = (payload.get("repository") or {}).get("id")
    if github_repo_id is None:
        return []
    return list(db.scalars(select(Repository).where(Repository.github_repo_id == github_repo_id)))


def _apply_workflow_run(
    db: Session, repositories: list[Repository], payload: dict[str, Any]
) -> None:
    run_payload = payload.get("workflow_run")
    if not run_payload:
        return
    run = github_api.as_workflow_run(run_payload)
    for repository in repositories:
        workflow_sync.record_runs(db, repository, [run])


def _mark_processed(db: Session, event_id: UUID) -> None:
    db.execute(update(WebhookEvent).where(WebhookEvent.id == event_id).values(processed=True))
    db.commit()
