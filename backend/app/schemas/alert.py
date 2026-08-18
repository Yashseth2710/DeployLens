from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repository_id: UUID
    kind: str
    subject: str
    detail: str
    issue_number: int | None
    issue_url: str | None
    raised_at: datetime
    resolved_at: datetime | None


class AlertActionOut(BaseModel):
    """What one pass decided, including the rendered issue text.

    The title and body are returned so a dry run can be read and judged before
    anything is written to GitHub — which is the only way to know the wording is
    right without publishing it first.
    """

    repository: str
    kind: str
    subject: str
    action: str
    title: str
    body: str
    issue_number: int | None
    issue_url: str | None


class AlertRunOut(BaseModel):
    raised: int
    resolved: int
    unchanged: int
    failed: int
    dry_run: bool
    actions: list[AlertActionOut]
