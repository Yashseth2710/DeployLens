from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.health import HealthCheck, HealthResult
from app.models.repository import Repository
from app.schemas.health import (
    HealthCheckCreate,
    HealthCheckOut,
    HealthCheckUpdate,
    HealthResultOut,
)
from app.services import probes

router = APIRouter(prefix="/api/health-checks", tags=["health"])

# Each endpoint costs a probe an hour, every hour, forever. Three per repository keeps
# a connected project's monitoring within the free compute budget.
MAX_PER_REPOSITORY = 3


@router.get("", response_model=list[HealthCheckOut])
def list_checks(
    user: CurrentUser, db: DbSession, repository_id: UUID | None = None
) -> list[HealthCheck]:
    query = (
        select(HealthCheck)
        .join(Repository, HealthCheck.repository_id == Repository.id)
        .where(Repository.user_id == user.id)
        .order_by(HealthCheck.created_at, HealthCheck.id)
    )
    if repository_id is not None:
        query = query.where(HealthCheck.repository_id == repository_id)
    return list(db.scalars(query))


@router.post("", response_model=HealthCheckOut, status_code=status.HTTP_201_CREATED)
def create_check(
    payload: HealthCheckCreate, user: CurrentUser, db: DbSession, background: BackgroundTasks
) -> HealthCheck:
    repository_id = payload.repository_id
    if _repository(db, user.id, repository_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connected repository")

    if _existing(db, repository_id, payload.url) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That URL is already being checked")

    if _count(db, repository_id) >= MAX_PER_REPOSITORY:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A repository can have at most {MAX_PER_REPOSITORY} health checks",
        )

    check = HealthCheck(
        repository_id=repository_id,
        url=payload.url,
        interval_minutes=payload.interval_minutes,
        expected_status=payload.expected_status,
    )
    db.add(check)
    db.commit()
    db.refresh(check)
    # Probed straight away, so the endpoint reports within seconds instead of reading as
    # unmeasured until the hourly runner comes round.
    background.add_task(probes.probe_once, check.id)
    return check


@router.get("/{check_id}/results", response_model=list[HealthResultOut])
def list_results(
    check_id: UUID,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[HealthResult]:
    if _owned(db, user.id, check_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such health check")

    return list(
        db.scalars(
            select(HealthResult)
            .where(HealthResult.health_check_id == check_id)
            .order_by(HealthResult.checked_at.desc())
            .limit(limit)
        )
    )


@router.patch("/{check_id}", response_model=HealthCheckOut)
def update_check(
    check_id: UUID,
    payload: HealthCheckUpdate,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
) -> HealthCheck:
    check = _owned(db, user.id, check_id)
    if check is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such health check")

    changes = payload.model_dump(exclude_unset=True)
    if "url" in changes and _existing(db, check.repository_id, changes["url"], skip=check.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "That URL is already being checked")

    for field, value in changes.items():
        setattr(check, field, value)
    db.commit()
    db.refresh(check)
    # A corrected URL is one nobody has measured yet, so it is read now rather than
    # left reporting the old address's failure for another hour.
    if "url" in changes:
        background.add_task(probes.probe_once, check.id)
    return check


@router.delete("/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_check(check_id: UUID, user: CurrentUser, db: DbSession) -> None:
    """Takes its recorded results with it, so uptime is never computed from a URL
    nobody is watching any more."""
    check = _owned(db, user.id, check_id)
    if check is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such health check")

    db.delete(check)
    db.commit()


def _repository(db: DbSession, user_id: UUID, repository_id: UUID) -> Repository | None:
    return db.scalar(
        select(Repository).where(Repository.id == repository_id, Repository.user_id == user_id)
    )


def _owned(db: DbSession, user_id: UUID, check_id: UUID) -> HealthCheck | None:
    return db.scalar(
        select(HealthCheck)
        .join(Repository, HealthCheck.repository_id == Repository.id)
        .where(HealthCheck.id == check_id, Repository.user_id == user_id)
    )


def _existing(
    db: DbSession, repository_id: UUID, url: str, skip: UUID | None = None
) -> UUID | None:
    query = select(HealthCheck.id).where(
        HealthCheck.repository_id == repository_id, HealthCheck.url == url
    )
    if skip is not None:
        query = query.where(HealthCheck.id != skip)
    return db.scalar(query)


def _count(db: DbSession, repository_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count(HealthCheck.id)).where(HealthCheck.repository_id == repository_id)
        )
        or 0
    )
