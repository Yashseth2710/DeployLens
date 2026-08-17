from typing import Any

from fastapi import APIRouter, BackgroundTasks

from app.api.deps import CurrentUser, DbSession, GitHubToken
from app.schemas.activity import ActivityBoardOut
from app.services import activity, autosync

# What the page waits before asking again is computed from the same function that decides
# when a repository is stale, so the two cannot drift — a poll slower than the throttle
# would make the throttle the real refresh rate, silently.

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.post("", response_model=ActivityBoardOut)
def refresh(
    user: CurrentUser, db: DbSession, token: GitHubToken, background: BackgroundTasks
) -> dict[str, Any]:
    """Answer with what we hold, then go and collect.

    Asking is still what keeps the data current, but the asker no longer waits for it.
    A pull is five seconds of GitHub round trips, and doing it before responding made
    every poll a five second page — for data that would have been on the next poll
    anyway. The board is read from the database and returned immediately; the pull runs
    after the response and lands within a poll or two.
    """
    background.add_task(autosync.collect_for, user.id, token)

    items = activity.board(db, user.id)
    state = autosync.collection_state(db, user.id)

    return {
        "items": items,
        "live_count": sum(1 for item in items if item.live),
        "last_synced_at": state.last_synced_at,
        "synced": state.repositories,
        "failed": state.failed,
        "poll_seconds": round(autosync.watching_interval(state.repositories).total_seconds()),
    }
