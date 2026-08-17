from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.security import decrypt_token, encrypt_token
from app.models.user import User
from app.services import github_oauth
from app.services.github_api import GitHubAuthExpiredError
from app.services.github_oauth import GitHubAuthError, TokenBundle

# Replaced this far ahead of expiry rather than on the failure itself. A token that dies
# mid-sweep would otherwise surface as an error the user has to read and act on, and the
# whole point is that they never find out an eight hour token exists.
RENEW_BEFORE = timedelta(minutes=15)


def store(db: Session, user: User, bundle: TokenBundle) -> None:
    user.access_token_encrypted = encrypt_token(bundle.access_token)
    user.access_token_expires_at = bundle.expires_at
    # GitHub rotates the refresh token on every use, and omits it entirely for apps that
    # do not expire tokens — keeping the old one in that case would be keeping a lie.
    if bundle.refresh_token:
        user.refresh_token_encrypted = encrypt_token(bundle.refresh_token)
    db.flush()


def access_token_for(db: Session, user: User) -> str:
    """The token to call GitHub with, renewed first if it is close to expiring.

    Every path that talks to GitHub goes through here, so nothing has to remember that
    tokens expire — including the scheduled sweep, which runs while nobody is watching
    and is exactly where a stale token would otherwise sit unnoticed.
    """
    if not _needs_renewal(user):
        return decrypt_token(user.access_token_encrypted)

    if not user.refresh_token_encrypted:
        raise GitHubAuthExpiredError("the stored GitHub token expired and cannot be renewed")

    try:
        bundle = github_oauth.refresh_access_token(decrypt_token(user.refresh_token_encrypted))
    except GitHubAuthError as exc:
        # The refresh token has its own six month life, and a user who revoked the app
        # invalidates both. Signing in again is the only way back.
        raise GitHubAuthExpiredError(str(exc)) from exc

    store(db, user, bundle)
    db.commit()
    return bundle.access_token


def _needs_renewal(user: User) -> bool:
    if user.access_token_expires_at is None:
        return False
    return datetime.now(UTC) >= user.access_token_expires_at - RENEW_BEFORE
