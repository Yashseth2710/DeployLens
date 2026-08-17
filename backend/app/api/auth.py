import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.cookies import (
    OAUTH_STATE_COOKIE,
    clear_session_cookie,
    clear_state_cookie,
    set_session_cookie,
    set_state_cookie,
)
from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.security import encrypt_token, issue_session
from app.models.user import User
from app.schemas.user import UserProfile
from app.services import github_oauth
from app.services.github_oauth import GitHubAccount, GitHubAuthError

router = APIRouter(prefix="/api/auth", tags=["auth"])

SIGNED_IN_PATH = "/repositories"
SIGN_IN_PATH = "/"


def _app_redirect(path: str, **params: str) -> str:
    url = f"{get_settings().app_url}{path}"
    return f"{url}?{urlencode(params)}" if params else url


@router.get("/github", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def start_sign_in() -> RedirectResponse:
    """The state value is handed to GitHub and mirrored into an httpOnly cookie. A
    forged callback cannot produce both halves, and the cookie is dropped on use."""
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(github_oauth.authorize_url(state))
    set_state_cookie(response, state)
    return response


@router.get("/github/callback", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def complete_sign_in(
    request: Request,
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)

    if error is not None:
        return _failed_sign_in("access_denied")
    if not code or not state or state != expected_state:
        return _failed_sign_in("invalid_state")

    try:
        access_token = github_oauth.exchange_code(code)
        account = github_oauth.fetch_account(access_token)
    except (GitHubAuthError, OSError):
        return _failed_sign_in("github_unavailable")

    user = _upsert_user(db, account, access_token)

    response = RedirectResponse(_app_redirect(SIGNED_IN_PATH))
    set_session_cookie(response, issue_session(user.id))
    clear_state_cookie(response)
    return response


@router.get("/me", response_model=UserProfile)
def current_user(user: CurrentUser) -> User:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(response: Response) -> None:
    clear_session_cookie(response)


def _failed_sign_in(reason: str) -> RedirectResponse:
    response = RedirectResponse(_app_redirect(SIGN_IN_PATH, auth_error=reason))
    clear_state_cookie(response)
    return response


def _upsert_user(db: DbSession, account: GitHubAccount, access_token: str) -> User:
    """Signing in again refreshes the profile and replaces the stored token, so a
    revoked or rescoped grant is picked up without a second table."""
    user = db.scalar(select(User).where(User.github_id == account.github_id))
    if user is None:
        user = User(github_id=account.github_id)
        db.add(user)

    user.username = account.username
    user.email = account.email
    user.avatar_url = account.avatar_url
    user.access_token_encrypted = encrypt_token(access_token)

    db.commit()
    db.refresh(user)
    return user
