from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
API_URL = "https://api.github.com"

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
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.post(
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
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {access_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(base_url=API_URL, headers=headers, timeout=_TIMEOUT) as client:
        profile = client.get("/user")
        if profile.status_code != httpx.codes.OK:
            raise GitHubAuthError("could not read the GitHub profile")
        data = profile.json()

        email = data.get("email")
        if email is None:
            email = _primary_email(client)

    return GitHubAccount(
        github_id=data["id"],
        username=data["login"],
        email=email,
        avatar_url=data.get("avatar_url"),
    )


def _primary_email(client: httpx.Client) -> str | None:
    """Users who hide their email get `null` on /user, so the verified primary address
    has to come from the dedicated endpoint."""
    response = client.get("/user/emails")
    if response.status_code != httpx.codes.OK:
        return None
    for entry in response.json():
        if entry.get("primary") and entry.get("verified"):
            address: str = entry["email"]
            return address
    return None
