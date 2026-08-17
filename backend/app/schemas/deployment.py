from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkflowRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    github_run_id: int
    workflow_name: str
    branch: str | None
    commit_sha: str | None
    status: str
    conclusion: str | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int | None
    html_url: str | None


class DeploymentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repository_id: UUID
    repository_full_name: str
    environment: str
    status: str
    branch: str | None
    commit_sha: str | None
    author: str | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int | None
    deployment_url: str | None


class DeploymentDetail(DeploymentSummary):
    workflow_run: WorkflowRunSummary | None


class SyncSummary(BaseModel):
    runs_seen: int
    runs_added: int
    deployments_added: int
    provider_deployments: int


class WorkflowRunRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repository_id: UUID
    repository_full_name: str
    github_run_id: int
    workflow_name: str
    branch: str | None
    commit_sha: str | None
    status: str
    conclusion: str | None
    event: str | None
    actor: str | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int | None
    html_url: str | None
