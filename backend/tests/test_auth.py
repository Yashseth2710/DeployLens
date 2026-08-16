import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cookies import OAUTH_STATE_COOKIE, SESSION_COOKIE
from app.core.security import decrypt_token, issue_session
from app.models.user import User
from app.services.github_oauth import ACCESS_TOKEN_URL, API_URL

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
