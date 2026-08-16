from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

SESSION_TTL = timedelta(days=7)
_JWT_ALGORITHM = "HS256"


def _fernet() -> Fernet:
    return Fernet(get_settings().token_encryption_key.encode())


def encrypt_token(raw_token: str) -> str:
    return _fernet().encrypt(raw_token.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("stored GitHub token could not be decrypted") from exc


def issue_session(user_id: UUID) -> str:
    """A signed cookie rather than a session row: reading it costs no database
    round-trip, which matters when every request runs in its own serverless process."""
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + SESSION_TTL}
    return jwt.encode(payload, get_settings().session_secret, algorithm=_JWT_ALGORITHM)


def read_session(token: str) -> UUID | None:
    try:
        payload = jwt.decode(token, get_settings().session_secret, algorithms=[_JWT_ALGORITHM])
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
