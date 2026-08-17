from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.services.github_api import GitHubError, client, get

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"

# An OAuth app with "expire user authorization tokens" switched on issues access tokens
# that die after eight hours and a refresh token to replace them with. An app without it
# issues tokens that never expire and no refresh token, so both shapes have to work.
REFRESH_GRANT = "refresh_token"

# `repo` covers private repositories and their Actions runs; `admin:repo_hook` is what
# lets DeployLens register its own webhook instead of the user adding one by hand.
SCOPES = "read:user user:email repo admin:repo_hook"

_TIMEOUT = httpx.Timeout(10.0)


class GitHubAuthError(Exception):
    pass


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None


@dataclass(frozen=True)
class GitHubAccount:
    github_id: int
    username: str
    email: str | None
    avatar_url: str | None


def authorize_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.app_url}/api/auth/github/callback",
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code: str) -> TokenBundle:
    settings = get_settings()
    return _token_request(
        {
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": f"{settings.app_url}/api/auth/github/callback",
        }
    )


def refresh_access_token(refresh_token: str) -> TokenBundle:
    """Trade a refresh token for a fresh access token without the user seeing anything.

    This is the whole reason expiry is invisible: an eight hour token would otherwise
    strand a signed-in user every working day, and the first they would know of it is
    the page quietly going stale.
    """
    settings = get_settings()
    return _token_request(
        {
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "grant_type": REFRESH_GRANT,
            "refresh_token": refresh_token,
        }
    )


def _token_request(data: dict[str, str]) -> TokenBundle:
    with httpx.Client(timeout=_TIMEOUT) as http:
        response = http.post(ACCESS_TOKEN_URL, headers={"Accept": "application/json"}, data=data)
    if response.status_code != httpx.codes.OK:
        raise GitHubAuthError("GitHub rejected the token request")

    body = response.json()
    # GitHub answers 200 with an `error` key when a code is spent or a refresh token has
    # itself expired, so the status line cannot be trusted on its own.
    if "access_token" not in body:
        raise GitHubAuthError(body.get("error_description", "no access token in response"))

    expires_in = body.get("expires_in")
    return TokenBundle(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token"),
        expires_at=(datetime.now(UTC) + timedelta(seconds=int(expires_in)) if expires_in else None),
    )


def fetch_account(access_token: str) -> GitHubAccount:
    try:
        with client(access_token) as http:
            profile = get(http, "/user")
            email = profile.get("email") or _primary_email(http)
    except GitHubError as exc:
        raise GitHubAuthError(str(exc)) from exc

    return GitHubAccount(
        github_id=profile["id"],
        username=profile["login"],
        email=email,
        avatar_url=profile.get("avatar_url"),
    )


def _primary_email(http: httpx.Client) -> str | None:
    """Users who hide their address get `null` on /user, so the verified primary one
    has to come from the dedicated endpoint. A user with none is signed in anyway."""
    try:
        entries = get(http, "/user/emails")
    except GitHubError:
        return None
    for entry in entries:
        if entry.get("primary") and entry.get("verified"):
            address: str = entry["email"]
            return address
    return None
