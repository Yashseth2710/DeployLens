from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.health import HealthCheck, HealthResult
from app.models.history import CommitWeek, PullRequest
from app.models.repository import Repository
from app.models.workflow import Deployment, WorkflowRun

# A cancelled or skipped run says nothing about whether the pipeline works, so the
# success rate is computed over decided outcomes only.
SUCCEEDED = ("success",)
FAILED = ("failure", "timed_out", "startup_failure", "error")

# Three deployments a week is the point where shipping looks continuous rather than
# occasional. Anything at or above it scores full marks for frequency.
TARGET_PER_WEEK = 3.0

# Deploy outcomes carry the most weight, but a project with CI and no release
# workflow is not unmeasurable: its runs are the delivery signal it does have.
WEIGHTS = {"deploys": 0.35, "runs": 0.25, "uptime": 0.25, "frequency": 0.15}


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
class PipelineMetrics:
    """Every Actions run, not only the ones that shipped. A pull request whose tests
    fail never becomes a deployment, but it is the thing a developer most wants to
    see, so it is measured separately rather than filtered away."""

    runs: int
    succeeded: int
    failed: int
    success_rate: float | None
    average_duration_seconds: int | None
    workflows: int
    branches: int
    last_run_at: datetime | None


EMPTY_PIPELINE = PipelineMetrics(0, 0, 0, None, None, 0, 0, None)


@dataclass(frozen=True)
class ReviewMetrics:
    """What went through review, and what it cost. `merge_rate` is measured over
    decided pull requests only — one still open has not failed, it has not finished."""

    opened: int
    merged: int
    closed_unmerged: int
    open_now: int
    merge_rate: float | None
    median_hours_to_merge: float | None
    commits: int
    commits_per_week: float
    first_commit_week: date | None


EMPTY_REVIEW = ReviewMetrics(0, 0, 0, 0, None, None, 0, 0.0, None)


@dataclass(frozen=True)
class RepositoryMetrics:
    repository_id: UUID
    full_name: str
    delivery: DeliveryMetrics
    pipeline: PipelineMetrics
    uptime: UptimeMetrics
    health_score: int | None


@dataclass(frozen=True)
class RunGroup:
    """Runs gathered under one name — a workflow, or a branch. The detail page reads
    both from the same shape, because the question is the same either way: what keeps
    failing, and what takes the longest."""

    name: str
    runs: int
    succeeded: int
    failed: int
    success_rate: float | None
    average_duration_seconds: int | None
    last_run_at: datetime | None


@dataclass(frozen=True)
class DeploymentPoint:
    day: date
    deployments: int
    succeeded: int
    failed: int
    average_duration_seconds: int | None


@dataclass(frozen=True)
class RunPoint:
    """A day of pipeline activity. Runs are the densest signal this product holds —
    a side project deploys weekly but runs CI many times a day — so this is the series
    that actually has a shape to read."""

    day: date
    runs: int
    succeeded: int
    failed: int
    average_duration_seconds: int | None


@dataclass(frozen=True)
class UptimePoint:
    day: date
    probes: int
    up: int
    uptime_percent: float


def health_score(
    delivery: DeliveryMetrics,
    uptime: UptimeMetrics,
    pipeline: PipelineMetrics | None = None,
) -> int | None:
    """A weighted blend of how often deploys succeed, how often runs pass, how often
    the app answers, and how regularly anything ships.

    Components with no data are dropped and the remaining weights renormalised, so a
    project with no health check is not scored as if it were down, and one with no
    release workflow is still scored on the runs it does have.
    """
    components = {
        "deploys": delivery.success_rate,
        "runs": pipeline.success_rate if pipeline else None,
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


def pipeline_metrics(db: Session, repository_ids: list[UUID], days: int) -> PipelineMetrics:
    if not repository_ids:
        return EMPTY_PIPELINE

    row = db.execute(
        select(
            func.count(WorkflowRun.id),
            func.count(case((WorkflowRun.conclusion.in_(SUCCEEDED), 1))),
            func.count(case((WorkflowRun.conclusion.in_(FAILED), 1))),
            func.avg(WorkflowRun.duration_seconds),
            func.count(func.distinct(WorkflowRun.workflow_name)),
            func.count(func.distinct(WorkflowRun.branch)),
            func.max(WorkflowRun.started_at),
        ).where(
            WorkflowRun.repository_id.in_(repository_ids),
            WorkflowRun.started_at >= _cutoff(days),
        )
    ).one()

    runs, succeeded, failed, average, workflows, branches, last_run = row
    decided = succeeded + failed
    return PipelineMetrics(
        runs=runs,
        succeeded=succeeded,
        failed=failed,
        success_rate=round(succeeded / decided * 100, 1) if decided else None,
        average_duration_seconds=round(average) if average else None,
        workflows=workflows,
        branches=branches,
        last_run_at=last_run,
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
    pipeline_by_repository = {
        repository_id: pipeline_metrics(db, [repository_id], days) for repository_id in ids
    }

    metrics = []
    for repository_id, full_name in repositories:
        delivery = delivery_by_repository.get(repository_id, EMPTY_DELIVERY)
        uptime = uptime_by_repository.get(repository_id, EMPTY_UPTIME)
        pipeline = pipeline_by_repository.get(repository_id, EMPTY_PIPELINE)
        metrics.append(
            RepositoryMetrics(
                repository_id=repository_id,
                full_name=full_name,
                delivery=delivery,
                pipeline=pipeline,
                uptime=uptime,
                health_score=health_score(delivery, uptime, pipeline),
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


def review_metrics(db: Session, repository_ids: list[UUID], days: int) -> ReviewMetrics:
    """Pull requests counted by what happened to them, and commits read from the weekly
    totals rather than a row per commit.

    Opened, merged and closed are counted in their own windows on purpose: a pull
    request opened before the window and merged inside it is a merge this month, and
    counting it only by when it opened would hide the work that just landed.
    """
    if not repository_ids:
        return EMPTY_REVIEW

    cutoff = _cutoff(days)
    scope = PullRequest.repository_id.in_(repository_ids)

    opened, merged, closed_unmerged, open_now = db.execute(
        select(
            func.count(case((PullRequest.opened_at >= cutoff, 1))),
            func.count(case((PullRequest.merged_at >= cutoff, 1))),
            func.count(
                case(((PullRequest.closed_at >= cutoff) & PullRequest.merged_at.is_(None), 1))
            ),
            func.count(case((PullRequest.state == "open", 1))),
        ).where(scope)
    ).one()

    median = db.scalar(
        select(
            func.percentile_cont(0.5).within_group(
                func.extract("epoch", PullRequest.merged_at - PullRequest.opened_at)
            )
        ).where(scope, PullRequest.merged_at >= cutoff, PullRequest.opened_at.is_not(None))
    )

    commits, first_week = db.execute(
        select(func.sum(CommitWeek.commits), func.min(CommitWeek.week_start)).where(
            CommitWeek.repository_id.in_(repository_ids),
            CommitWeek.week_start >= _date_cutoff(days),
        )
    ).one()
    earliest = db.scalar(
        select(func.min(CommitWeek.week_start)).where(CommitWeek.repository_id.in_(repository_ids))
    )

    decided = merged + closed_unmerged
    total_commits = int(commits or 0)
    return ReviewMetrics(
        opened=opened,
        merged=merged,
        closed_unmerged=closed_unmerged,
        open_now=open_now,
        merge_rate=round(merged / decided * 100, 1) if decided else None,
        # Hours, because "two days to merge" is a different sentence from "51 hours",
        # and the client is the one that should choose which to print.
        median_hours_to_merge=round(median / 3600, 1) if median else None,
        commits=total_commits,
        commits_per_week=round(total_commits / days * 7, 2),
        first_commit_week=earliest or first_week,
    )


def run_groups(
    db: Session, repository_id: UUID, days: int, by: InstrumentedAttribute[Any], limit: int = 20
) -> list[RunGroup]:
    """Busiest first, so a repository with fifty branches still leads with the ones
    worth reading. Runs with no branch recorded are left out rather than collected
    under an invented name."""
    rows = db.execute(
        select(
            by,
            func.count(WorkflowRun.id),
            func.count(case((WorkflowRun.conclusion.in_(SUCCEEDED), 1))),
            func.count(case((WorkflowRun.conclusion.in_(FAILED), 1))),
            func.avg(WorkflowRun.duration_seconds),
            func.max(WorkflowRun.started_at),
        )
        .where(
            WorkflowRun.repository_id == repository_id,
            WorkflowRun.started_at >= _cutoff(days),
            by.is_not(None),
        )
        .group_by(by)
        .order_by(func.count(WorkflowRun.id).desc(), by)
        .limit(limit)
    ).all()

    groups = []
    for name, runs, succeeded, failed, average, last_run in rows:
        decided = succeeded + failed
        groups.append(
            RunGroup(
                name=name,
                runs=runs,
                succeeded=succeeded,
                failed=failed,
                success_rate=round(succeeded / decided * 100, 1) if decided else None,
                average_duration_seconds=round(average) if average else None,
                last_run_at=last_run,
            )
        )
    return groups


def first_activity_at(db: Session, repository_id: UUID) -> datetime | None:
    """The oldest run held for this repository, whatever the window. It is how the page
    says how far back it can actually see, rather than implying it holds everything."""
    return db.scalar(
        select(func.min(WorkflowRun.started_at)).where(WorkflowRun.repository_id == repository_id)
    )


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


def run_series(db: Session, repository_ids: list[UUID], days: int) -> list[RunPoint]:
    """One row per day that ran anything. Days with no runs are left out rather than
    returned as zero, the same as every other series here: a day nobody pushed is not a
    day the pipeline scored nothing, and the chart is what decides how to draw the gap."""
    if not repository_ids:
        return []

    day = func.date_trunc("day", WorkflowRun.started_at)
    rows = db.execute(
        select(
            day.label("day"),
            func.count(WorkflowRun.id),
            func.count(case((WorkflowRun.conclusion.in_(SUCCEEDED), 1))),
            func.count(case((WorkflowRun.conclusion.in_(FAILED), 1))),
            func.avg(WorkflowRun.duration_seconds),
        )
        .where(
            WorkflowRun.repository_id.in_(repository_ids),
            WorkflowRun.started_at >= _cutoff(days),
        )
        .group_by(day)
        .order_by(day)
    ).all()

    return [
        RunPoint(
            day=point.date(),
            runs=total,
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


def _date_cutoff(days: int) -> date:
    """Commit weeks are dates, not timestamps, so they need a date to compare against
    rather than the database's own clock."""
    return (datetime.now(UTC) - timedelta(days=days)).date()


def _cutoff(days: int) -> ColumnElement[Any]:
    return func.now() - func.make_interval(0, 0, 0, days)
