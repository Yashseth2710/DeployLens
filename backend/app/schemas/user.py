from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    github_id: int
    username: str
    email: str | None
    avatar_url: str | None
