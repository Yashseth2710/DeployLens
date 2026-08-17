from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, GitHubToken
from app.schemas.activity import ActivityBoardOut
from app.services import activity, autosync

# What the page waits before asking again is computed from the same function that decides
# when a repository is stale, so the two cannot drift — a poll slower than the throttle
# would make the throttle the real refresh rate, silently.

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.post("", response_model=ActivityBoardOut)
def refresh(user: CurrentUser, db: DbSession, token: GitHubToken) -> dict[str, Any]:
    """Read the board, and pull anything stale while we are here.

    Asking is what keeps the data current, and asking happens on a timer — this is the
    only path data arrives by while somebody is watching, so there is nothing to press.
    """
    report = autosync.refresh_user(db, user, token)
    items = activity.board(db, user.id)
    connected = report.synced + report.skipped + report.failed

    return {
        "items": items,
        "live_count": sum(1 for item in items if item.live),
        "last_synced_at": report.last_synced_at,
        "synced": report.synced,
        "failed": report.failed,
        "poll_seconds": round(autosync.watching_interval(connected).total_seconds()),
    }
