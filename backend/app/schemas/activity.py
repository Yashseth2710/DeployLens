from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ActivityItemOut(BaseModel):
    kind: str
    id: UUID
    repository_id: UUID
    repository_full_name: str
    title: str
    detail: str | None
    status: str
    conclusion: str | None
    live: bool
    started_at: datetime | None
    completed_at: datetime | None
    url: str | None


class ActivityBoardOut(BaseModel):
    items: list[ActivityItemOut]
    live_count: int
    last_synced_at: datetime | None
    synced: int
    failed: int
    poll_seconds: int


class SweepSummary(BaseModel):
    synced: int
    skipped: int
    failed: int
    runs_added: int
    deployments_added: int
