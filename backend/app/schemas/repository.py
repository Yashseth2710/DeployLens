from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConnectedRepository(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    github_repo_id: int
    name: str
    full_name: str
    owner: str
    default_branch: str
    github_url: str
    connected_at: datetime


class AvailableRepository(BaseModel):
    github_repo_id: int
    name: str
    full_name: str
    owner: str
    default_branch: str
    github_url: str
    private: bool
    pushed_at: datetime | None
    connected: bool
    # The picker disconnects by our own row id, so returning it here saves the
    # client a second request just to map GitHub's id onto ours.
    connected_id: UUID | None


class ConnectRepositoryRequest(BaseModel):
    github_repo_id: int
