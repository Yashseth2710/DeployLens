"""Telling somebody a pipeline broke, without them having to open the dashboard.

The dashboard answers "what is wrong" for a person already looking. This answers
the same question for a person who is not, which is most of the time — and it does
it by writing to the one place a developer already reads about their own repository.

Only genuinely broken pipelines raise an alert. A workflow failing three times in a
row, or failing a third of the time over a real sample, is something somebody has to
go and fix. Flaky tests and slowdowns are worth reading on a dashboard but do not
justify an issue in somebody's repository: an alerting system that cries wolf gets
muted, and a muted alert is worth less than none.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.alert import Alert
from app.models.repository import Repository
from app.models.user import User
from app.services import github_api, insights, tokens
from app.services.github_api import GitHubAuthExpiredError, GitHubError
from app.services.insights import Finding

# What is worth an issue. These are the two findings that mean a pipeline is broken
# rather than imperfect; the other three stay on the dashboard where they belong.
ALERTING_KINDS = frozenset({"streak", "chronic"})

# The label the issues are filed under, so a repository owner can filter them out or
# subscribe to them without touching anything else.
LABEL = "deploylens"


@dataclass(frozen=True)
class AlertAction:
    """One decision the sweep reached, and whether it was carried out.

    A dry run fills everything here except the issue: the alert is decided, the
    title and body are rendered, and nothing is sent. That is what makes the
    output reviewable before a single write reaches GitHub.
    """

    repository: str
    kind: str
    subject: str
    action: str
    title: str
    body: str
    issue_number: int | None = None
    issue_url: str | None = None


@dataclass(frozen=True)
class AlertRun:
    raised: int
    resolved: int
    unchanged: int
    failed: int
    dry_run: bool
    actions: list[AlertAction]


def sweep(db: Session, days: int, *, dry_run: bool = True) -> AlertRun:
    """Check every connected repository and reconcile its alerts.

    Runs per user rather than per repository so one expired token cannot stop
    everybody else's alerts, the same way the collection sweep behaves.
    """
    raised: list[AlertAction] = []
    resolved: list[AlertAction] = []
    unchanged = 0
    failed = 0

    for user in db.scalars(select(User)):
        try:
            token = tokens.access_token_for(db, user)
        except (ValueError, GitHubAuthExpiredError):
            # A token that cannot be read or renewed is a sign-in problem for this
            # user alone. Everybody else still gets their alerts.
            continue

        repositories = db.scalars(select(Repository).where(Repository.user_id == user.id))
        for repository in repositories:
            try:
                report = _reconcile(db, repository, token, days, dry_run=dry_run)
            except GitHubError:
                # GitHub refusing one repository — archived, permissions changed,
                # rate limited — must not stop the rest of the sweep.
                failed += 1
                continue
            raised.extend(report.raised)
            resolved.extend(report.resolved)
            unchanged += report.unchanged

    if dry_run:
        # A preview that left rows behind would be worse than useless: the next real
        # sweep would read them as already handled and file nothing at all.
        db.rollback()
    else:
        db.commit()

    return AlertRun(
        raised=len(raised),
        resolved=len(resolved),
        unchanged=unchanged,
        failed=failed,
        dry_run=dry_run,
        actions=[*raised, *resolved],
    )


@dataclass(frozen=True)
class _Report:
    raised: list[AlertAction]
    resolved: list[AlertAction]
    unchanged: int


def _reconcile(
    db: Session, repository: Repository, token: str, days: int, *, dry_run: bool
) -> _Report:
    """Bring one repository's alerts in line with what is currently true of it.

    Three things can be true of a problem: it is new, it is still standing, or it
    has stopped. Each gets one action and no more — an issue that is already open
    is not opened again, and a problem that has not changed says nothing at all.
    """
    # A workflow failing six times running is both a streak and a chronic failure, and
    # findings arrive severity-ordered. Keyed by subject alone, the first one wins and
    # the second is dropped: one broken workflow is one problem and earns one issue,
    # however many ways the detector can describe it.
    standing: dict[str, Finding] = {}
    for finding in insights.findings_for(db, repository.id, days):
        if finding.kind in ALERTING_KINDS:
            standing.setdefault(finding.subject, finding)

    open_alerts = list(
        db.scalars(
            select(Alert).where(Alert.repository_id == repository.id, Alert.resolved_at.is_(None))
        )
    )
    already = {alert.subject: alert for alert in open_alerts}

    raised: list[AlertAction] = []
    resolved: list[AlertAction] = []
    unchanged = 0

    for key, finding in standing.items():
        if key in already:
            unchanged += 1
            continue
        raised.append(_raise(db, repository, finding, token, days, dry_run=dry_run))

    for key, alert in already.items():
        if key not in standing:
            resolved.append(_resolve(db, repository, alert, token, days, dry_run=dry_run))

    return _Report(raised=raised, resolved=resolved, unchanged=unchanged)


def _raise(
    db: Session, repository: Repository, finding: Finding, token: str, days: int, *, dry_run: bool
) -> AlertAction:
    """Record a new problem and, unless this is a dry run, file it."""
    title = _title(finding)
    body = _body(repository, finding, days)

    alert = Alert(
        repository_id=repository.id,
        kind=finding.kind,
        subject=finding.subject,
        detail=finding.detail,
        raised_at=datetime.now(UTC),
    )

    if not dry_run:
        issue = github_api.create_issue(token, repository.full_name, title, body, [LABEL])
        alert.issue_number = issue.number
        alert.issue_url = issue.url

    db.add(alert)
    db.flush()
    return AlertAction(
        repository=repository.full_name,
        kind=finding.kind,
        subject=finding.subject,
        action="raise",
        title=title,
        body=body,
        issue_number=alert.issue_number,
        issue_url=alert.issue_url,
    )


def _resolve(
    db: Session, repository: Repository, alert: Alert, token: str, days: int, *, dry_run: bool
) -> AlertAction:
    """Close a problem that has stopped happening.

    The comment matters as much as the close: an issue that shuts silently reads
    as somebody having dismissed it, not as the pipeline having recovered.
    """
    body = (
        f"Recovered. `{alert.subject}` is no longer {_phrase(alert.kind)} "
        f"in the last {days} days of runs.\n\n"
        "Closed automatically by DeployLens."
    )

    if not dry_run and alert.issue_number is not None:
        github_api.close_issue(token, repository.full_name, alert.issue_number, body)

    alert.resolved_at = datetime.now(UTC)
    db.flush()
    return AlertAction(
        repository=repository.full_name,
        kind=alert.kind,
        subject=alert.subject,
        action="resolve",
        title=f"Recovered: {alert.subject}",
        body=body,
        issue_number=alert.issue_number,
        issue_url=alert.issue_url,
    )


def _title(finding: Finding) -> str:
    """What the issue is called in a notification list, where it may be all somebody
    reads. The subject leads because that is the part they will recognise."""
    if finding.kind == "streak":
        return f"{finding.subject} is failing repeatedly"
    return f"{finding.subject} is failing {finding.failed} of {finding.runs} runs"


def _body(repository: Repository, finding: Finding, days: int) -> str:
    """The issue itself: what was measured, over what, and where to look.

    Written as a statement of evidence rather than an instruction. The person
    reading it knows their own pipeline better than this does.
    """
    lines = [
        # The detail is written to sit after a subject on the dashboard — "CI ·
        # failing 6 runs in a row" — so it starts lowercase. Here it opens the
        # issue and has to stand as its own sentence.
        f"`{finding.subject}` is {finding.detail}.",
        "",
        f"- **Repository:** {repository.full_name}",
        f"- **Runs read:** {finding.runs} in the last {days} days",
        f"- **Failed:** {finding.failed}",
    ]
    if finding.last_seen_at:
        lines.append(f"- **Last seen:** {finding.last_seen_at:%Y-%m-%d %H:%M} UTC")
    if finding.run_url:
        lines.append(f"- **The run:** {finding.run_url}")

    lines += [
        "",
        f"[Open this project in DeployLens]({get_settings().app_url}/repositories/{repository.id})",
        "",
        "Raised automatically by DeployLens, which closes this issue when the pipeline recovers.",
    ]
    return "\n".join(lines)


def _phrase(kind: str) -> str:
    return "failing repeatedly" if kind == "streak" else "failing often"


def recent(db: Session, user_id: UUID, limit: int) -> list[Alert]:
    """What has been raised lately, newest first, for the page that shows it."""
    return list(
        db.scalars(
            select(Alert)
            .join(Repository, Repository.id == Alert.repository_id)
            .where(Repository.user_id == user_id)
            .order_by(Alert.raised_at.desc())
            .limit(limit)
        )
    )
