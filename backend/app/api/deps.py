from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.cookies import SESSION_COOKIE
from app.core.security import read_session
from app.database.session import get_db
from app.models.user import User

DbSession = Annotated[Session, Depends(get_db)]


def require_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in with GitHub to continue")
    return user


CurrentUser = Annotated[User, Depends(require_user)]
