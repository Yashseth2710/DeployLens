from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PullRequestRow(BaseModel):
    id: UUID
    repository_id: UUID
    repository_full_name: str
    number: int
    title: str
    author: str | None
    # Ours, not GitHub's: merged and abandoned are both "closed" to GitHub, and the
    # difference between them is the reason this list exists.
    outcome: str
    draft: bool
    head_branch: str | None
    base_branch: str | None
    html_url: str | None
    opened_at: datetime | None
    merged_at: datetime | None
    closed_at: datetime | None
