from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.health import HealthCheck, HealthResult
from app.models.repository import Repository
from app.models.workflow import Deployment

# A cancelled or skipped run says nothing about whether the pipeline works, so the
# success rate is computed over decided outcomes only.
SUCCEEDED = ("success",)
FAILED = ("failure", "timed_out", "startup_failure")

# Three deployments a week is the point where shipping looks continuous rather than
# occasional. Anything at or above it scores full marks for frequency.
TARGET_PER_WEEK = 3.0

WEIGHTS = {"success": 0.5, "uptime": 0.3, "frequency": 0.2}


@dataclass(frozen=True)
class DeliveryMetrics:
    deployments: int
    succeeded: int
    failed: int
    success_rate: float | None
    average_duration_seconds: int | None
    deployments_per_week: float
    last_deployment_at: datetime | None


EMPTY_DELIVERY = DeliveryMetrics(0, 0, 0, None, None, 0.0, None)


@dataclass(frozen=True)
class UptimeMetrics:
    monitored_urls: int
    probes: int
    up: int
    uptime_percent: float | None
    average_response_time_ms: int | None


EMPTY_UPTIME = UptimeMetrics(0, 0, 0, None, None)


@dataclass(frozen=True)
class RepositoryMetrics:
    repository_id: UUID
    full_name: str
    delivery: DeliveryMetrics
    uptime: UptimeMetrics
    health_score: int | None


@dataclass(frozen=True)
class DeploymentPoint:
    day: date
    deployments: int
    succeeded: int
    failed: int
    average_duration_seconds: int | None


@dataclass(frozen=True)
class UptimePoint:
    day: date
    probes: int
    up: int
    uptime_percent: float


def health_score(delivery: DeliveryMetrics, uptime: UptimeMetrics) -> int | None:
    """A weighted blend of how often deploys succeed, how often the app answers, and
    how regularly anything ships.

    Components with no data are dropped and the remaining weights renormalised, so a
    project that has not configured a health check is not scored as if it were down.
    """
    components = {
        "success": delivery.success_rate,
        "uptime": uptime.uptime_percent,
        "frequency": min(delivery.deployments_per_week / TARGET_PER_WEEK, 1.0) * 100
        if delivery.deployments
        else None,
    }
    scored = {name: value for name, value in components.items() if value is not None}
    if not scored:
        return None

    total_weight = sum(WEIGHTS[name] for name in scored)
    weighted = sum(WEIGHTS[name] * value for name, value in scored.items())
    return round(weighted / total_weight)


def delivery_metrics(db: Session, repository_ids: list[UUID], days: int) -> DeliveryMetrics:
    if not repository_ids:
        return EMPTY_DELIVERY

    row = db.execute(
        _within_window(
            select(
                func.count(Deployment.id),
                func.count(case((Deployment.status.in_(SUCCEEDED), 1))),
                func.count(case((Deployment.status.in_(FAILED), 1))),
                func.avg(Deployment.duration_seconds),
                func.max(Deployment.started_at),
            ),
            repository_ids,
            days,
        )
    ).one()

    total, succeeded, failed, average_duration, last_deployment = row
    return _delivery_from(total, succeeded, failed, average_duration, last_deployment, days)


def uptime_metrics(db: Session, repository_ids: list[UUID], days: int) -> UptimeMetrics:
    if not repository_ids:
        return EMPTY_UPTIME

    monitored = db.scalar(
        select(func.count(HealthCheck.id)).where(
            HealthCheck.repository_id.in_(repository_ids), HealthCheck.enabled.is_(True)
        )
    )
    probes, up, average_response = db.execute(
        select(
            func.count(HealthResult.id),
            func.count(case((HealthResult.status == "up", 1))),
            func.avg(HealthResult.response_time_ms),
        )
        .join(HealthCheck, HealthResult.health_check_id == HealthCheck.id)
        .where(
            HealthCheck.repository_id.in_(repository_ids),
            HealthResult.checked_at >= _cutoff(days),
        )
    ).one()

    return _uptime_from(monitored or 0, probes, up, average_response)


def _delivery_from(
    total: int,
    succeeded: int,
    failed: int,
    average_duration: float | None,
    last_deployment: datetime | None,
    days: int,
) -> DeliveryMetrics:
    decided = succeeded + failed
    return DeliveryMetrics(
        deployments=total,
        succeeded=succeeded,
        failed=failed,
        success_rate=round(succeeded / decided * 100, 1) if decided else None,
        average_duration_seconds=round(average_duration) if average_duration else None,
        deployments_per_week=round(total / days * 7, 2),
        last_deployment_at=last_deployment,
    )


def _uptime_from(
    monitored_urls: int, probes: int, up: int, average_response: float | None
) -> UptimeMetrics:
    return UptimeMetrics(
        monitored_urls=monitored_urls,
        probes=probes,
        up=up,
        uptime_percent=round(up / probes * 100, 2) if probes else None,
        average_response_time_ms=round(average_response) if average_response else None,
    )


def per_repository(db: Session, user_id: UUID, days: int) -> list[RepositoryMetrics]:
    """Three grouped queries rather than two per repository. The dashboard asks for
    this on every load, and each round trip is one more thing Neon has to wake for."""
    repositories = db.execute(
        select(Repository.id, Repository.full_name)
        .where(Repository.user_id == user_id)
        .order_by(Repository.full_name)
    ).all()
    if not repositories:
        return []

    ids = [repository_id for repository_id, _ in repositories]
    delivery_by_repository = _delivery_by_repository(db, ids, days)
    uptime_by_repository = _uptime_by_repository(db, ids, days)

    metrics = []
    for repository_id, full_name in repositories:
        delivery = delivery_by_repository.get(repository_id, EMPTY_DELIVERY)
        uptime = uptime_by_repository.get(repository_id, EMPTY_UPTIME)
        metrics.append(
            RepositoryMetrics(
                repository_id=repository_id,
                full_name=full_name,
                delivery=delivery,
                uptime=uptime,
                health_score=health_score(delivery, uptime),
            )
        )
    return metrics


def _delivery_by_repository(
    db: Session, repository_ids: list[UUID], days: int
) -> dict[UUID, DeliveryMetrics]:
    rows = db.execute(
        _within_window(
            select(
                Deployment.repository_id,
                func.count(Deployment.id),
                func.count(case((Deployment.status.in_(SUCCEEDED), 1))),
                func.count(case((Deployment.status.in_(FAILED), 1))),
                func.avg(Deployment.duration_seconds),
                func.max(Deployment.started_at),
            ),
            repository_ids,
            days,
        ).group_by(Deployment.repository_id)
    ).all()

    return {row[0]: _delivery_from(row[1], row[2], row[3], row[4], row[5], days) for row in rows}


def _uptime_by_repository(
    db: Session, repository_ids: list[UUID], days: int
) -> dict[UUID, UptimeMetrics]:
    enabled_urls: dict[UUID, int] = {
        repository_id: urls
        for repository_id, urls in db.execute(
            select(HealthCheck.repository_id, func.count(HealthCheck.id))
            .where(HealthCheck.repository_id.in_(repository_ids), HealthCheck.enabled.is_(True))
            .group_by(HealthCheck.repository_id)
        ).all()
    }
    rows = db.execute(
        select(
            HealthCheck.repository_id,
            func.count(HealthResult.id),
            func.count(case((HealthResult.status == "up", 1))),
            func.avg(HealthResult.response_time_ms),
        )
        .join(HealthCheck, HealthResult.health_check_id == HealthCheck.id)
        .where(
            HealthCheck.repository_id.in_(repository_ids),
            HealthResult.checked_at >= _cutoff(days),
        )
        .group_by(HealthCheck.repository_id)
    ).all()

    measured = {
        repository_id: _uptime_from(enabled_urls.get(repository_id, 0), probes, up, average)
        for repository_id, probes, up, average in rows
    }
    for repository_id, urls in enabled_urls.items():
        measured.setdefault(repository_id, UptimeMetrics(urls, 0, 0, None, None))
    return measured


def deployment_series(db: Session, repository_ids: list[UUID], days: int) -> list[DeploymentPoint]:
    """One row per day that had deployments. Empty days are left out rather than
    fabricated - the chart decides how to draw a gap, not the API."""
    if not repository_ids:
        return []

    day = func.date_trunc("day", Deployment.started_at)
    rows = db.execute(
        _within_window(
            select(
                day.label("day"),
                func.count(Deployment.id),
                func.count(case((Deployment.status.in_(SUCCEEDED), 1))),
                func.count(case((Deployment.status.in_(FAILED), 1))),
                func.avg(Deployment.duration_seconds),
            ),
            repository_ids,
            days,
        )
        .group_by(day)
        .order_by(day)
    ).all()

    return [
        DeploymentPoint(
            day=point.date(),
            deployments=total,
            succeeded=succeeded,
            failed=failed,
            average_duration_seconds=round(average) if average else None,
        )
        for point, total, succeeded, failed, average in rows
    ]


def uptime_series(db: Session, repository_ids: list[UUID], days: int) -> list[UptimePoint]:
    if not repository_ids:
        return []

    day = func.date_trunc("day", HealthResult.checked_at)
    rows = db.execute(
        select(
            day.label("day"),
            func.count(HealthResult.id),
            func.count(case((HealthResult.status == "up", 1))),
        )
        .join(HealthCheck, HealthResult.health_check_id == HealthCheck.id)
        .where(
            HealthCheck.repository_id.in_(repository_ids),
            HealthResult.checked_at >= _cutoff(days),
        )
        .group_by(day)
        .order_by(day)
    ).all()

    return [
        UptimePoint(
            day=point.date(),
            probes=probes,
            up=up,
            uptime_percent=round(up / probes * 100, 2),
        )
        for point, probes, up in rows
    ]


def _within_window(query: Select[Any], repository_ids: list[UUID], days: int) -> Select[Any]:
    return query.where(
        Deployment.repository_id.in_(repository_ids),
        Deployment.started_at >= _cutoff(days),
    )


def _cutoff(days: int) -> ColumnElement[Any]:
    return func.now() - func.make_interval(0, 0, 0, days)
