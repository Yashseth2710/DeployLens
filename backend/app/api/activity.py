from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, GitHubToken
from app.schemas.activity import ActivityBoardOut
from app.services import activity, autosync

# What the page waits before asking again. Sent by the server rather than fixed in the
# client so the two cadences cannot drift apart: something running is worth watching
# closely, and an idle account is not worth waking the database for every few seconds.
LIVE_POLL_SECONDS = 10
IDLE_POLL_SECONDS = 45

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.post("", response_model=ActivityBoardOut)
def refresh(
    user: CurrentUser, db: DbSession, token: GitHubToken, force: bool = False
) -> dict[str, Any]:
    """Read the board, and pull anything stale while we are here.

    Asking is what keeps the data current — there is no button in this path. `force`
    is the manual recovery the "Sync now" control uses when someone wants to be sure
    rather than wait for the throttle.
    """
    report = autosync.refresh_user(db, user, token, force=force)
    items = activity.board(db, user.id)
    live = [item for item in items if item.live]

    return {
        "items": items,
        "live_count": len(live),
        "last_synced_at": report.last_synced_at,
        "synced": report.synced,
        "failed": report.failed,
        "poll_seconds": LIVE_POLL_SECONDS if live else IDLE_POLL_SECONDS,
    }
