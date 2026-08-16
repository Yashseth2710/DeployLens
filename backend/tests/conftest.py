from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.cookies import SESSION_COOKIE
from app.core.security import encrypt_token, issue_session
from app.database.session import SessionLocal, engine, get_db
from app.main import app
from app.models.user import User

ACCESS_TOKEN = "gho_test_token"


@pytest.fixture
def db() -> Iterator[Session]:
    """Every test runs inside a transaction that is rolled back, so the suite can point
    at a real Postgres without leaving rows behind."""
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user(db: Session) -> User:
    account = User(
        github_id=4815162342,
        username="octocat",
        email="octocat@example.com",
        access_token_encrypted=encrypt_token(ACCESS_TOKEN),
    )
    db.add(account)
    db.flush()
    return account


@pytest.fixture
def signed_in(client: TestClient, user: User) -> User:
    client.cookies.set(SESSION_COOKIE, issue_session(user.id))
    return user
