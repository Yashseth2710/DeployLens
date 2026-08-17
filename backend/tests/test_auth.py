import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cookies import OAUTH_STATE_COOKIE, SESSION_COOKIE
from app.core.security import decrypt_token, issue_session
from app.models.user import User
from app.services.github_api import API_URL
from app.services.github_oauth import ACCESS_TOKEN_URL

ACCOUNT = {
    "id": 4815162342,
    "login": "octocat",
    "email": None,
    "avatar_url": "https://avatars.githubusercontent.com/u/583231",
}
EMAILS = [
    {"email": "old@example.com", "primary": False, "verified": True},
    {"email": "octocat@example.com", "primary": True, "verified": True},
]


@pytest.fixture
def github_grants_access():
    with respx.mock(assert_all_called=False) as mock:
        mock.post(ACCESS_TOKEN_URL).respond(json={"access_token": "gho_live", "scope": "repo"})
        mock.get(f"{API_URL}/user").respond(json=ACCOUNT)
        mock.get(f"{API_URL}/user/emails").respond(json=EMAILS)
        yield mock


def sign_in(client: TestClient) -> httpx.Response:
    client.get("/api/auth/github")
    state = client.cookies[OAUTH_STATE_COOKIE]
    return client.get("/api/auth/github/callback", params={"code": "abc123", "state": state})


def test_sign_in_sends_the_user_to_github_with_a_matching_state_cookie(client: TestClient):
    response = client.get("/api/auth/github")

    assert response.status_code == 307
    location = httpx.URL(response.headers["location"])
    assert location.host == "github.com"
    assert location.params["state"] == client.cookies[OAUTH_STATE_COOKIE]
    assert "admin:repo_hook" in location.params["scope"]


def test_callback_stores_the_account_and_opens_a_session(
    client: TestClient, db: Session, github_grants_access
):
    response = sign_in(client)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/dashboard")
    assert SESSION_COOKIE in client.cookies

    user = db.scalar(select(User).where(User.github_id == ACCOUNT["id"]))
    assert user is not None
    assert user.username == "octocat"
    assert user.email == "octocat@example.com"
    assert user.access_token_encrypted != "gho_live"
    assert decrypt_token(user.access_token_encrypted) == "gho_live"


def test_signing_in_twice_refreshes_the_same_account(
    client: TestClient, db: Session, github_grants_access
):
    sign_in(client)
    github_grants_access.get(f"{API_URL}/user").respond(json={**ACCOUNT, "login": "renamed"})
    sign_in(client)

    users = db.scalars(select(User).where(User.github_id == ACCOUNT["id"])).all()
    assert len(users) == 1
    assert users[0].username == "renamed"


def test_callback_refuses_a_state_that_does_not_match_the_cookie(client: TestClient):
    client.get("/api/auth/github")

    response = client.get("/api/auth/github/callback", params={"code": "abc123", "state": "forged"})

    assert "auth_error=invalid_state" in response.headers["location"]
    assert SESSION_COOKIE not in client.cookies


def test_callback_reports_a_denied_authorization(client: TestClient):
    client.get("/api/auth/github")
    state = client.cookies[OAUTH_STATE_COOKIE]

    response = client.get(
        "/api/auth/github/callback", params={"error": "access_denied", "state": state}
    )

    assert "auth_error=access_denied" in response.headers["location"]


@respx.mock
def test_callback_survives_github_rejecting_the_code(client: TestClient):
    respx.post(ACCESS_TOKEN_URL).respond(json={"error": "bad_verification_code"})
    client.get("/api/auth/github")
    state = client.cookies[OAUTH_STATE_COOKIE]

    response = client.get("/api/auth/github/callback", params={"code": "spent", "state": state})

    assert "auth_error=github_unavailable" in response.headers["location"]
    assert SESSION_COOKIE not in client.cookies


def test_me_needs_a_session(client: TestClient):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_the_signed_in_profile(client: TestClient, github_grants_access):
    sign_in(client)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == "octocat"


def test_a_session_for_a_deleted_user_is_not_accepted(client: TestClient, db: Session):
    orphan = User(github_id=99, username="ghost", access_token_encrypted="x")
    db.add(orphan)
    db.flush()
    client.cookies.set(SESSION_COOKIE, issue_session(orphan.id))
    db.delete(orphan)
    db.flush()

    assert client.get("/api/auth/me").status_code == 401


def test_logout_clears_the_session(client: TestClient, github_grants_access):
    sign_in(client)

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_a_token_near_expiry_is_renewed_before_it_is_used(
    db: Session, monkeypatch: pytest.MonkeyPatch
):
    """The whole reason expiry is invisible. An eight hour token would otherwise strand
    a signed-in user every working day, and the first they would know of it is the page
    quietly going stale."""
    from datetime import UTC, datetime, timedelta

    from app.core.security import decrypt_token, encrypt_token
    from app.services import tokens
    from app.services.github_oauth import TokenBundle

    user = User(
        github_id=771001,
        username="octocat",
        access_token_encrypted=encrypt_token("old-token"),
        refresh_token_encrypted=encrypt_token("refresh-token"),
        access_token_expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    db.add(user)
    db.flush()

    monkeypatch.setattr(
        tokens.github_oauth,
        "refresh_access_token",
        lambda refresh: TokenBundle(
            access_token="new-token",
            refresh_token="rotated-refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=8),
        ),
        raising=True,
    )

    assert tokens.access_token_for(db, user) == "new-token"
    # GitHub rotates the refresh token on every use; keeping the old one would strand
    # the next renewal.
    assert decrypt_token(user.refresh_token_encrypted) == "rotated-refresh"


def test_a_token_with_no_expiry_is_never_refreshed(db: Session, monkeypatch: pytest.MonkeyPatch):
    """An OAuth app without token expiry issues no refresh token at all, and asking
    GitHub to refresh nothing would fail every request."""
    from app.core.security import encrypt_token
    from app.services import tokens

    user = User(
        github_id=771002,
        username="octocat",
        access_token_encrypted=encrypt_token("forever-token"),
    )
    db.add(user)
    db.flush()

    monkeypatch.setattr(tokens.github_oauth, "refresh_access_token", _never, raising=True)

    assert tokens.access_token_for(db, user) == "forever-token"


def test_an_unrenewable_expired_token_asks_for_a_fresh_sign_in(db: Session):
    from datetime import UTC, datetime, timedelta

    from app.core.security import encrypt_token
    from app.services import tokens
    from app.services.github_api import GitHubAuthExpiredError

    user = User(
        github_id=771003,
        username="octocat",
        access_token_encrypted=encrypt_token("dead-token"),
        access_token_expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(user)
    db.flush()

    with pytest.raises(GitHubAuthExpiredError):
        tokens.access_token_for(db, user)


def _never(refresh: str):
    raise AssertionError("a token that never expires must not be refreshed")
