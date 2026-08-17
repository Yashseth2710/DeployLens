import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.deps import DbSession
from app.core.config import get_settings
from app.schemas.activity import SweepSummary
from app.schemas.health import ProbeRunSummary
from app.services import autosync, probes
from app.services.autosync import RefreshReport
from app.services.probes import ProbeRun

router = APIRouter(prefix="/api/cron", tags=["cron"])


def require_cron_secret(authorization: Annotated[str | None, Header()] = None) -> None:
    """The scheduler is outside the app, so this endpoint is reachable by anyone who
    finds it. An unset secret refuses everything rather than running for free."""
    secret = get_settings().cron_secret
    presented = (authorization or "").removeprefix("Bearer ")
    if not secret or not hmac.compare_digest(secret, presented):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cron secret does not match")


@router.post(
    "/health-check",
    response_model=ProbeRunSummary,
    dependencies=[Depends(require_cron_secret)],
)
def run_health_checks(db: DbSession) -> ProbeRun:
    """Every due URL is probed in one invocation. Batching matters more than it looks:
    the database is woken once per run rather than once per check."""
    return probes.run_due_probes(db)


@router.post(
    "/sync",
    response_model=SweepSummary,
    dependencies=[Depends(require_cron_secret)],
)
def sync_everything(db: DbSession) -> RefreshReport:
    """Collect for the hours when nobody has the page open. Without this, a repository
    is only ever as current as the last time somebody looked at it."""
    return autosync.refresh_everyone(db)
