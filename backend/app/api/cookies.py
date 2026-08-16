from fastapi import Response

from app.core.config import get_settings
from app.core.security import SESSION_TTL

SESSION_COOKIE = "deploylens_session"
OAUTH_STATE_COOKIE = "deploylens_oauth_state"
STATE_TTL_SECONDS = 600


def _secure() -> bool:
    return get_settings().app_url.startswith("https://")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=_secure(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def set_state_cookie(response: Response, state: str) -> None:
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=_secure(),
        samesite="lax",
        path="/",
    )


def clear_state_cookie(response: Response) -> None:
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
