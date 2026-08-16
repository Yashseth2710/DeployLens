from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.services.github_api import GitHubError, client, get

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"

# `repo` covers private repositories and their Actions runs; `admin:repo_hook` is what
# lets DeployLens register its own webhook instead of the user adding one by hand.
SCOPES = "read:user user:email repo admin:repo_hook"

_TIMEOUT = httpx.Timeout(10.0)


class GitHubAuthError(Exception):
    pass


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


def exchange_code(code: str) -> str:
    settings = get_settings()
    with httpx.Client(timeout=_TIMEOUT) as http:
        response = http.post(
            ACCESS_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": f"{settings.app_url}/api/auth/github/callback",
            },
        )
    if response.status_code != httpx.codes.OK:
        raise GitHubAuthError("GitHub rejected the authorization code exchange")

    body = response.json()
    # GitHub answers 200 with an `error` key when the code is expired or already spent.
    if "access_token" not in body:
        raise GitHubAuthError(body.get("error_description", "no access token in response"))
    token: str = body["access_token"]
    return token


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
