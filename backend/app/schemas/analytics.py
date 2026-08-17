from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.repository import ConnectedRepository


class DeliveryMetricsOut(BaseModel):
    deployments: int
    succeeded: int
    failed: int
    success_rate: float | None
    average_duration_seconds: int | None
    deployments_per_week: float
    last_deployment_at: datetime | None


class UptimeMetricsOut(BaseModel):
    monitored_urls: int
    probes: int
    up: int
    uptime_percent: float | None
    average_response_time_ms: int | None


class PipelineMetricsOut(BaseModel):
    runs: int
    succeeded: int
    failed: int
    success_rate: float | None
    average_duration_seconds: int | None
    workflows: int
    branches: int
    last_run_at: datetime | None


class RepositoryMetricsOut(BaseModel):
    repository_id: UUID
    full_name: str
    delivery: DeliveryMetricsOut
    pipeline: PipelineMetricsOut
    uptime: UptimeMetricsOut
    health_score: int | None


class DeploymentPointOut(BaseModel):
    day: date
    deployments: int
    succeeded: int
    failed: int
    average_duration_seconds: int | None


class UptimePointOut(BaseModel):
    day: date
    probes: int
    up: int
    uptime_percent: float


class OverviewOut(BaseModel):
    window_days: int
    connected_repositories: int
    delivery: DeliveryMetricsOut
    pipeline: PipelineMetricsOut
    uptime: UptimeMetricsOut
    health_score: int | None
    repositories: list[RepositoryMetricsOut]


class RunGroupOut(BaseModel):
    name: str
    runs: int
    succeeded: int
    failed: int
    success_rate: float | None
    average_duration_seconds: int | None
    last_run_at: datetime | None


class RepositoryDetailOut(BaseModel):
    repository: ConnectedRepository
    window_days: int
    delivery: DeliveryMetricsOut
    pipeline: PipelineMetricsOut
    uptime: UptimeMetricsOut
    health_score: int | None
    workflows: list[RunGroupOut]
    branches: list[RunGroupOut]
    first_activity_at: datetime | None


class TrendOut(BaseModel):
    window_days: int
    deployments: list[DeploymentPointOut]
    uptime: list[UptimePointOut]
