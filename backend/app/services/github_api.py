from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

API_URL = "https://api.github.com"
PER_PAGE = 100
MAX_PAGES = 5

_TIMEOUT = httpx.Timeout(15.0)


class GitHubError(Exception):
    """GitHub could not answer the request."""


class GitHubAuthExpiredError(GitHubError):
    """The stored token was revoked or its grant was withdrawn."""


class GitHubRateLimitError(GitHubError):
    """The hourly quota for this token is spent."""


class GitHubNotFoundError(GitHubError):
    """The resource does not exist, or the token cannot see it — GitHub does not
    distinguish the two, on purpose."""


@dataclass(frozen=True)
class GitHubRepository:
    github_repo_id: int
    name: str
    full_name: str
    owner: str
    default_branch: str
    github_url: str
    private: bool
    pushed_at: str | None


@dataclass(frozen=True)
class GitHubWorkflowRun:
    github_run_id: int
    workflow_name: str
    branch: str | None
    commit_sha: str | None
    status: str
    conclusion: str | None
    event: str
    actor: str | None
    started_at: datetime | None
    completed_at: datetime | None
    html_url: str | None


@contextmanager
def client(access_token: str) -> Iterator[httpx.Client]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {access_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(base_url=API_URL, headers=headers, timeout=_TIMEOUT) as http:
        yield http


def get(http: httpx.Client, path: str, **params: Any) -> Any:
    try:
        response = http.get(path, params=params or None)
    except httpx.HTTPError as exc:
        raise GitHubError(str(exc)) from exc
    _raise_for_status(response)
    return response.json()


def list_repositories(access_token: str) -> list[GitHubRepository]:
    """Sorted by last push so the repositories worth connecting come first. Paging stops
    at MAX_PAGES; nobody picking three to ten projects needs to scroll past 500."""
    repositories: list[GitHubRepository] = []
    with client(access_token) as http:
        for page in range(1, MAX_PAGES + 1):
            batch = get(
                http,
                "/user/repos",
                per_page=PER_PAGE,
                page=page,
                sort="pushed",
                affiliation="owner,collaborator,organization_member",
            )
            repositories.extend(as_repository(item) for item in batch)
            if len(batch) < PER_PAGE:
                break
    return repositories


def get_repository(access_token: str, github_repo_id: int) -> GitHubRepository:
    """Looked up by id rather than by the name the client sent, so a connect request
    cannot claim a repository the token has no access to."""
    with client(access_token) as http:
        return as_repository(get(http, f"/repositories/{github_repo_id}"))


def list_workflow_runs(
    access_token: str, full_name: str, pages: int = 1
) -> list[GitHubWorkflowRun]:
    """Newest first, which is the order GitHub returns. One page of 100 is enough to
    keep an existing repository current; a first connect asks for more."""
    runs: list[GitHubWorkflowRun] = []
    with client(access_token) as http:
        for page in range(1, min(pages, MAX_PAGES) + 1):
            payload = get(http, f"/repos/{full_name}/actions/runs", per_page=PER_PAGE, page=page)
            batch = payload.get("workflow_runs", [])
            runs.extend(as_workflow_run(item) for item in batch)
            if len(batch) < PER_PAGE:
                break
    return runs


def as_workflow_run(payload: dict[str, Any]) -> GitHubWorkflowRun:
    conclusion = payload.get("conclusion")
    return GitHubWorkflowRun(
        github_run_id=payload["id"],
        workflow_name=payload.get("name") or "Workflow",
        branch=payload.get("head_branch"),
        commit_sha=payload.get("head_sha"),
        status=payload.get("status") or "queued",
        conclusion=conclusion,
        event=payload.get("event") or "",
        actor=(payload.get("actor") or {}).get("login"),
        started_at=_timestamp(payload.get("run_started_at") or payload.get("created_at")),
        # GitHub reports no completion time of its own; updated_at is the last thing
        # that happened to the run, which for a finished run is it finishing.
        completed_at=_timestamp(payload.get("updated_at")) if conclusion else None,
        html_url=payload.get("html_url"),
    )


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def as_repository(payload: dict[str, Any]) -> GitHubRepository:
    return GitHubRepository(
        github_repo_id=payload["id"],
        name=payload["name"],
        full_name=payload["full_name"],
        owner=payload["owner"]["login"],
        default_branch=payload.get("default_branch") or "main",
        github_url=payload["html_url"],
        private=payload.get("private", False),
        pushed_at=payload.get("pushed_at"),
    )


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == httpx.codes.UNAUTHORIZED:
        raise GitHubAuthExpiredError("the stored GitHub token is no longer valid")
    if (
        response.status_code in (httpx.codes.FORBIDDEN, httpx.codes.TOO_MANY_REQUESTS)
        and response.headers.get("x-ratelimit-remaining") == "0"
    ):
        raise GitHubRateLimitError("GitHub rate limit reached for this token")
    if response.status_code == httpx.codes.NOT_FOUND:
        raise GitHubNotFoundError(f"GitHub has nothing at {response.request.url.path}")
    if response.status_code >= httpx.codes.BAD_REQUEST:
        path = response.request.url.path
        raise GitHubError(f"GitHub responded {response.status_code} for {path}")
