import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.health import HealthCheck, HealthResult

# One invocation has to finish inside the serverless timeout, so the batch is capped and
# ordered by the longest wait. Anything left over is picked up by the next run.
MAX_PROBES_PER_RUN = 25
PROBE_TIMEOUT = httpx.Timeout(10.0)
RESULT_RETENTION_DAYS = 30


@dataclass(frozen=True)
class ProbeOutcome:
    status: str
    status_code: int | None
    response_time_ms: int | None
    error_message: str | None


@dataclass(frozen=True)
class ProbeRun:
    checked: int
    up: int
    down: int
    pruned: int


def run_due_probes(db: Session) -> ProbeRun:
    checks = due_checks(db)
    up = 0
    for check in checks:
        outcome = probe(check.url, check.expected_status)
        db.add(
            HealthResult(
                health_check_id=check.id,
                status=outcome.status,
                status_code=outcome.status_code,
                response_time_ms=outcome.response_time_ms,
                error_message=outcome.error_message,
            )
        )
        up += outcome.status == "up"
    pruned = prune_old_results(db)
    db.commit()

    return ProbeRun(checked=len(checks), up=up, down=len(checks) - up, pruned=pruned)


def due_checks(db: Session) -> list[HealthCheck]:
    """Due means never probed, or last probed longer ago than its own interval. The
    runner fires more often than the shortest interval and this decides who is owed a
    probe, so a slower check is not dragged up to the schedule's cadence."""
    last_checked = (
        select(func.max(HealthResult.checked_at))
        .where(HealthResult.health_check_id == HealthCheck.id)
        .scalar_subquery()
    )
    interval = func.make_interval(0, 0, 0, 0, 0, HealthCheck.interval_minutes)

    return list(
        db.scalars(
            select(HealthCheck)
            .where(
                HealthCheck.enabled.is_(True),
                or_(last_checked.is_(None), last_checked <= func.now() - interval),
            )
            .order_by(last_checked.asc().nullsfirst())
            .limit(MAX_PROBES_PER_RUN)
        )
    )


def probe(url: str, expected_status: int) -> ProbeOutcome:
    """A URL is only stored after its host passed validation, but DNS can be repointed
    at a private address afterwards, so the resolved address is checked again here."""
    host = urlsplit(url).hostname
    if host is None or not resolves_publicly(host):
        return ProbeOutcome("down", None, None, "Host does not resolve to a public address")

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT, follow_redirects=True) as http:
            response = http.get(url, headers={"User-Agent": "DeployLens-HealthCheck/1.0"})
    except httpx.HTTPError as exc:
        return ProbeOutcome("down", None, _elapsed_ms(started), type(exc).__name__)

    elapsed = _elapsed_ms(started)
    code = response.status_code
    if code == expected_status:
        return ProbeOutcome("up", code, elapsed, None)
    return ProbeOutcome("down", code, elapsed, f"Expected {expected_status}, got {code}")


def resolves_publicly(host: str) -> bool:
    try:
        addresses = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in addresses)


def prune_old_results(db: Session) -> int:
    """Results are the only table that grows without an upper bound. A month is enough
    for the uptime window the dashboard shows."""
    cutoff = func.now() - func.make_interval(0, 0, 0, RESULT_RETENTION_DAYS)
    swept = db.execute(
        delete(HealthResult).where(HealthResult.checked_at < cutoff).returning(HealthResult.id)
    ).all()
    return len(swept)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
