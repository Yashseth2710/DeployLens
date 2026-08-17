from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
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


@dataclass(frozen=True)
class GitHubDeployment:
    github_deployment_id: int
    environment: str
    ref: str | None
    commit_sha: str | None
    creator: str | None
    state: str
    deployment_url: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class GitHubPullRequest:
    number: int
    title: str
    author: str | None
    state: str
    draft: bool
    head_branch: str | None
    base_branch: str | None
    html_url: str | None
    opened_at: datetime | None
    updated_at: datetime | None
    merged_at: datetime | None
    closed_at: datetime | None


@dataclass(frozen=True)
class GitHubCommitWeek:
    """One week of commits. Kept as a total rather than a row per commit: the questions
    this product asks are about volume and rhythm, and storing every commit message
    would be a lot of rows to answer none of them."""

    week_start: date
    commits: int


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


def post(http: httpx.Client, path: str, body: dict[str, Any]) -> Any:
    try:
        response = http.post(path, json=body)
    except httpx.HTTPError as exc:
        raise GitHubError(str(exc)) from exc
    _raise_for_status(response)
    return response.json()


def delete(http: httpx.Client, path: str) -> None:
    try:
        response = http.delete(path)
    except httpx.HTTPError as exc:
        raise GitHubError(str(exc)) from exc
    _raise_for_status(response)


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


def list_pull_requests(
    access_token: str, full_name: str, pages: int = 1
) -> list[GitHubPullRequest]:
    """Every state, sorted by when each was last touched, so one page holds whatever has
    moved recently and a first connect can reach back for the rest.

    A closed pull request with no `merged_at` was abandoned, and that distinction is the
    whole point of collecting these: it is the difference between work that shipped and
    work that did not.
    """
    pull_requests: list[GitHubPullRequest] = []
    with client(access_token) as http:
        for page in range(1, min(pages, MAX_PAGES) + 1):
            batch = get(
                http,
                f"/repos/{full_name}/pulls",
                per_page=PER_PAGE,
                page=page,
                state="all",
                sort="updated",
                direction="desc",
            )
            pull_requests.extend(as_pull_request(item) for item in batch)
            if len(batch) < PER_PAGE:
                break
    return pull_requests


def commit_activity(access_token: str, full_name: str) -> list[GitHubCommitWeek]:
    """A year of weekly commit totals in one request.

    GitHub computes this asynchronously and answers 202 with an empty body while it
    works, which is not an error — it means ask again shortly. An empty list is the
    honest answer for now, and the next sync collects it.
    """
    with client(access_token) as http:
        try:
            response = http.get(f"/repos/{full_name}/stats/commit_activity")
        except httpx.HTTPError as exc:
            raise GitHubError(str(exc)) from exc
        if response.status_code == httpx.codes.ACCEPTED:
            return []
        _raise_for_status(response)
        payload = response.json()

    if not isinstance(payload, list):
        return []
    return [
        GitHubCommitWeek(
            week_start=datetime.fromtimestamp(week["week"], tz=UTC).date(),
            commits=week.get("total", 0),
        )
        for week in payload
        if week.get("week") is not None
    ]


def as_pull_request(payload: dict[str, Any]) -> GitHubPullRequest:
    return GitHubPullRequest(
        number=payload["number"],
        title=payload.get("title") or "",
        author=(payload.get("user") or {}).get("login"),
        state=payload.get("state") or "open",
        draft=bool(payload.get("draft")),
        head_branch=(payload.get("head") or {}).get("ref"),
        base_branch=(payload.get("base") or {}).get("ref"),
        html_url=payload.get("html_url"),
        opened_at=_timestamp(payload.get("created_at")),
        updated_at=_timestamp(payload.get("updated_at")),
        merged_at=_timestamp(payload.get("merged_at")),
        closed_at=_timestamp(payload.get("closed_at")),
    )


def create_webhook(access_token: str, full_name: str, callback_url: str, secret: str) -> None:
    """Only `workflow_run` is subscribed. Every other event would cost a delivery, a
    row and a signature check to reach the same conclusion: nothing to record.

    A repository reconnected after being dropped still carries its old hook, so an
    existing one is left alone rather than creating a second delivery of everything.
    """
    with client(access_token) as http:
        if _webhook_id(http, full_name, callback_url) is not None:
            return
        post(
            http,
            f"/repos/{full_name}/hooks",
            {
                "name": "web",
                "active": True,
                "events": ["workflow_run"],
                "config": {
                    "url": callback_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
        )


def delete_webhook(access_token: str, full_name: str, callback_url: str) -> None:
    """Found by its callback URL rather than a stored id, which keeps the hook out of
    the schema and off the disconnect path when GitHub has already forgotten it."""
    with client(access_token) as http:
        hook_id = _webhook_id(http, full_name, callback_url)
        if hook_id is not None:
            delete(http, f"/repos/{full_name}/hooks/{hook_id}")


def _webhook_id(http: httpx.Client, full_name: str, callback_url: str) -> int | None:
    for hook in get(http, f"/repos/{full_name}/hooks", per_page=PER_PAGE):
        if hook.get("config", {}).get("url") == callback_url:
            hook_id: int = hook["id"]
            return hook_id
    return None


def list_deployments(
    access_token: str,
    full_name: str,
    limit: int = 30,
    settled_ids: frozenset[int] = frozenset(),
) -> list[GitHubDeployment]:
    """GitHub records what Vercel, Netlify and every other provider integration
    shipped, whether or not an Actions workflow was involved.

    Each deployment's state is a second call, so a naive read of thirty deployments
    costs thirty one requests. `settled_ids` names the ones already stored in a final
    state — those never change again, so they are skipped and a repository that has not
    deployed lately costs a single request instead of dozens.
    """
    deployments: list[GitHubDeployment] = []
    with client(access_token) as http:
        for payload in get(http, f"/repos/{full_name}/deployments", per_page=limit):
            if payload["id"] in settled_ids:
                continue
            statuses = get(
                http, f"/repos/{full_name}/deployments/{payload['id']}/statuses", per_page=1
            )
            latest = statuses[0] if statuses else {}
            deployments.append(
                GitHubDeployment(
                    github_deployment_id=payload["id"],
                    environment=payload.get("environment") or "production",
                    ref=payload.get("ref"),
                    commit_sha=payload.get("sha"),
                    creator=(payload.get("creator") or {}).get("login"),
                    state=latest.get("state") or "pending",
                    deployment_url=latest.get("environment_url") or latest.get("target_url"),
                    created_at=_timestamp(payload.get("created_at")),
                    updated_at=_timestamp(latest.get("created_at") or payload.get("updated_at")),
                )
            )
    return deployments


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
