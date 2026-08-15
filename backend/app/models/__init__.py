"""Importing every model here is what lets Alembic autogenerate see the full schema."""

from app.models.health import HealthCheck, HealthResult
from app.models.repository import Repository
from app.models.user import User
from app.models.webhook import WebhookEvent
from app.models.workflow import Deployment, WorkflowRun

__all__ = [
    "Deployment",
    "HealthCheck",
    "HealthResult",
    "Repository",
    "User",
    "WebhookEvent",
    "WorkflowRun",
]
