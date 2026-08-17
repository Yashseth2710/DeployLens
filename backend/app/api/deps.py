from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.cookies import SESSION_COOKIE
from app.core.security import read_session
from app.database.session import get_db
from app.models.user import User
from app.services import tokens

DbSession = Annotated[Session, Depends(get_db)]


def require_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in with GitHub to continue")
    return user


CurrentUser = Annotated[User, Depends(require_user)]


def github_token(user: CurrentUser, db: DbSession) -> str:
    """The token to call GitHub with, renewed here if it is near expiry so no route has
    to know that tokens expire at all.

    A key rotation leaves old ciphertext unreadable. That is a sign-in problem, not a
    server error, so the user is sent back through OAuth to store a fresh token.
    """
    try:
        return tokens.access_token_for(db, user)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sign in with GitHub again to refresh access"
        ) from exc


GitHubToken = Annotated[str, Depends(github_token)]
