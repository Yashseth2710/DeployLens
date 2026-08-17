import ipaddress
from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Hourly is the floor: every probe wakes Neon and holds it awake through the idle
# window, so cadence is what the free compute budget is actually spent on.
Interval = Annotated[int, Field(ge=60, le=1440)]
ExpectedStatus = Annotated[int, Field(ge=100, le=599)]

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "instance-data"}


def public_url(value: str) -> str:
    """The probe runs on our infrastructure, so an unchecked URL turns the app into a
    request forwarder. Loopback, private and link-local targets are refused."""
    parts = urlsplit(value.strip())
    if parts.scheme not in _ALLOWED_SCHEMES or not parts.hostname:
        raise ValueError("Give a full http:// or https:// URL")

    host = parts.hostname.lower()
    if host in _BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("That host is not reachable from the internet")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return value.strip()
    if not address.is_global:
        raise ValueError("That address is not reachable from the internet")
    return value.strip()


class HealthCheckCreate(BaseModel):
    repository_id: UUID
    url: str
    interval_minutes: Interval = 60
    expected_status: ExpectedStatus = 200

    _check_url = field_validator("url")(public_url)


class HealthCheckUpdate(BaseModel):
    url: str | None = None
    interval_minutes: Interval | None = None
    expected_status: ExpectedStatus | None = None
    enabled: bool | None = None

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        return public_url(value) if value is not None else None


class HealthCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repository_id: UUID
    url: str
    interval_minutes: int
    expected_status: int
    enabled: bool
    created_at: datetime


class HealthResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    health_check_id: UUID
    status: str
    status_code: int | None
    response_time_ms: int | None
    error_message: str | None
    checked_at: datetime


class ProbeRunSummary(BaseModel):
    checked: int
    up: int
    down: int
    pruned: int
