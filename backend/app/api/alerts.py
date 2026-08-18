from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.models.alert import Alert
from app.schemas.alert import AlertOut, AlertRunOut
from app.services import alerts
from app.services.alerts import AlertRun

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

WindowDays = Annotated[int, Query(ge=1, le=90)]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get("", response_model=list[AlertOut])
def list_alerts(user: CurrentUser, db: DbSession, limit: Limit = 20) -> list[Alert]:
    """What has been raised, newest first, whether or not it is still standing."""
    return alerts.recent(db, user.id, limit)


@router.post("/preview", response_model=AlertRunOut)
def preview(user: CurrentUser, db: DbSession, days: WindowDays = 30) -> AlertRun:
    """Decide what would be filed, and file nothing.

    Alerts write to somebody's repository, which is not a thing to find out about
    afterwards. This renders the exact issues the sweep would open — title, body
    and all — so the wording can be read and judged before any of it is published.
    """
    return alerts.sweep(db, days, dry_run=True)
