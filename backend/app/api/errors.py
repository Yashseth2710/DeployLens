from collections.abc import Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.github_api import (
    GitHubAuthExpiredError,
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)

Handler = Callable[[Request, Exception], JSONResponse]

_STATUS_BY_ERROR = {
    GitHubAuthExpiredError: (
        status.HTTP_401_UNAUTHORIZED,
        "GitHub access was revoked, sign in again",
    ),
    GitHubNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "Your GitHub account cannot see that repository",
    ),
    GitHubRateLimitError: (
        status.HTTP_429_TOO_MANY_REQUESTS,
        "GitHub rate limit reached, try again later",
    ),
    GitHubError: (status.HTTP_502_BAD_GATEWAY, "GitHub could not be reached"),
}


def install_github_error_handlers(app: FastAPI) -> None:
    """Every route that talks to GitHub fails the same handful of ways, so the
    translation lives here instead of in a try block around each call."""
    for error, (code, detail) in _STATUS_BY_ERROR.items():
        app.add_exception_handler(error, _respond(code, detail))


def _respond(code: int, detail: str) -> Handler:
    def handle(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=code, content={"detail": detail})

    return handle
