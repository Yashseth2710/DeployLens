from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.workflow import WorkflowRun
from app.services.metrics import FAILED, SUCCEEDED

# Below this a run count is anecdote rather than pattern. Three failures out of four
# runs is worth saying; one out of one is a bad afternoon.
MIN_RUNS = 4

# A workflow that fails a third of the time is unreliable even if it mostly works,
# because the third is what somebody has to go and read.
CHRONIC_FAILURE_RATE = 30.0

# Two consecutive failures is noise between one person's commits. Three is a branch
# nobody has fixed.
MIN_STREAK = 3

# Recent runs have to take half again as long as the window's earlier ones before
# this is a slowdown rather than a slow week.
SLOWDOWN_FACTOR = 1.5
MIN_SLOWDOWN_SECONDS = 30

# Findings are ranked so the sheet leads with what costs the most attention.
SEVERITY = {"streak": 0, "flaky": 1, "chronic": 2, "branch": 3, "slowdown": 4}


@dataclass(frozen=True)
class Finding:
    """One thing worth doing something about, said in the terms a developer would use.

    `subject` is the workflow or branch it is about, `detail` is the sentence the UI
    prints, and `run_url` points at the newest failing run behind it so the finding
    can be opened rather than only read.
    """

    kind: str
    subject: str
    detail: str
    runs: int
    failed: int
    last_seen_at: datetime | None
    run_url: str | None


@dataclass(frozen=True)
class RepositoryFindings:
    repository_id: UUID
    full_name: str
    findings: list[Finding]


def findings_for(db: Session, repository_id: UUID, days: int) -> list[Finding]:
    """Every signal the stored runs can support, ranked with the loudest first.

    Nothing here asks GitHub anything: a run already carries its workflow, branch,
    commit and conclusion, and the patterns worth naming are all comparisons between
    rows that are already sitting in the table.
    """
    runs = _completed_runs(db, repository_id, days)
    if not runs:
        return []

    findings = [
        *_flaky(runs),
        *_chronic(runs),
        *_streaks(runs),
        *_slowdowns(runs),
        *_broken_branches(runs),
    ]
    return sorted(findings, key=lambda finding: (SEVERITY[finding.kind], -finding.failed))


def across_repositories(
    db: Session, user_id: UUID, days: int, per_repository: int
) -> list[RepositoryFindings]:
    """The same reading for every connected project, so the dashboard can name the one
    that needs attention without the user opening each card to find it."""
    repositories = db.execute(
        select(Repository.id, Repository.full_name)
        .where(Repository.user_id == user_id)
        .order_by(Repository.full_name)
    ).all()

    found = []
    for repository_id, full_name in repositories:
        findings = findings_for(db, repository_id, days)
        if findings:
            found.append(
                RepositoryFindings(
                    repository_id=repository_id,
                    full_name=full_name,
                    findings=findings[:per_repository],
                )
            )
    return found


def _completed_runs(db: Session, repository_id: UUID, days: int) -> list[WorkflowRun]:
    """Decided runs only, newest first. A run still in flight has no verdict to read,
    and a cancelled one says nothing about whether the workflow works."""
    return list(
        db.scalars(
            select(WorkflowRun)
            .where(
                WorkflowRun.repository_id == repository_id,
                WorkflowRun.conclusion.in_((*SUCCEEDED, *FAILED)),
                WorkflowRun.started_at >= func.now() - func.make_interval(0, 0, 0, days),
            )
            .order_by(WorkflowRun.started_at.desc())
        )
    )


def _flaky(runs: list[WorkflowRun]) -> list[Finding]:
    """A workflow that both passed and failed on the same commit.

    This is the one signal that is not a judgement call. The code did not change
    between those two runs, so whatever differed was the pipeline itself — and a
    developer who reruns until it goes green has learned nothing about their branch.
    """
    by_workflow: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for run in runs:
        if run.commit_sha:
            by_workflow[run.workflow_name][run.commit_sha].add(_verdict(run))

    findings = []
    for workflow, commits in by_workflow.items():
        contradicted = [sha for sha, verdicts in commits.items() if len(verdicts) > 1]
        if not contradicted:
            continue

        failures = [
            run
            for run in runs
            if run.workflow_name == workflow
            and run.commit_sha in contradicted
            and _verdict(run) == "failed"
        ]
        findings.append(
            Finding(
                kind="flaky",
                subject=workflow,
                detail=(
                    f"passed and failed on the same commit "
                    f"{_count(len(contradicted), 'time', 'times')}"
                ),
                runs=len(commits),
                failed=len(contradicted),
                last_seen_at=failures[0].started_at if failures else None,
                run_url=failures[0].html_url if failures else None,
            )
        )
    return findings


def _chronic(runs: list[WorkflowRun]) -> list[Finding]:
    """A workflow that fails often enough to be untrustworthy, and has failed recently.

    Both halves matter. A workflow fixed a fortnight ago still carries its old failure
    rate for the rest of the window, and reporting it as broken sends somebody to read
    logs that were already dealt with.
    """
    findings = []
    for workflow, group in _grouped(runs, lambda run: run.workflow_name).items():
        failures = [run for run in group if _verdict(run) == "failed"]
        if len(group) < MIN_RUNS or not failures:
            continue

        rate = len(failures) / len(group) * 100
        if rate < CHRONIC_FAILURE_RATE:
            continue

        # Runs are newest-first, so the head of the list is the recent stretch. A
        # workflow that has not failed anywhere in it has been fixed, whatever the
        # window's average still says.
        recent = group[: max(MIN_RUNS, len(group) // 3)]
        if not any(_verdict(run) == "failed" for run in recent):
            continue

        findings.append(
            Finding(
                kind="chronic",
                subject=workflow,
                detail=f"fails {round(rate)}% of the time",
                runs=len(group),
                failed=len(failures),
                last_seen_at=failures[0].started_at,
                run_url=failures[0].html_url,
            )
        )
    return findings


def _streaks(runs: list[WorkflowRun]) -> list[Finding]:
    """Consecutive failures right now, per workflow.

    A rate averages the whole window and can look survivable while the thing is
    simply broken. The streak is the question a developer actually asks first: is it
    failing at this moment, and for how long.
    """
    findings = []
    for workflow, group in _grouped(runs, lambda run: run.workflow_name).items():
        streak = 0
        for run in group:
            if _verdict(run) != "failed":
                break
            streak += 1

        if streak < MIN_STREAK:
            continue

        findings.append(
            Finding(
                kind="streak",
                subject=workflow,
                detail=f"failing {_count(streak, 'run', 'runs')} in a row",
                runs=len(group),
                failed=streak,
                last_seen_at=group[0].started_at,
                run_url=group[0].html_url,
            )
        )
    return findings


def _slowdowns(runs: list[WorkflowRun]) -> list[Finding]:
    """A workflow whose recent runs take materially longer than its own earlier ones.

    Measured against itself rather than any absolute threshold, because a five-minute
    build is fine for one project and a regression for another. Only the runs that
    passed are timed: a failure that stops early is fast for the wrong reason.
    """
    findings = []
    for workflow, group in _grouped(runs, lambda run: run.workflow_name).items():
        timed = [
            (run, run.duration_seconds)
            for run in group
            if _verdict(run) == "passed" and run.duration_seconds
        ]
        if len(timed) < MIN_RUNS * 2:
            continue

        half = len(timed) // 2
        recent = _mean(seconds for _, seconds in timed[:half])
        earlier = _mean(seconds for _, seconds in timed[half:])
        if recent < earlier * SLOWDOWN_FACTOR or recent - earlier < MIN_SLOWDOWN_SECONDS:
            continue

        newest, _ = timed[0]

        findings.append(
            Finding(
                kind="slowdown",
                subject=workflow,
                detail=(
                    f"{_minutes(earlier)} to {_minutes(recent)}, "
                    f"{round(recent / earlier, 1)} times slower"
                ),
                runs=len(timed),
                failed=0,
                last_seen_at=newest.started_at,
                run_url=newest.html_url,
            )
        )
    return findings


def _broken_branches(runs: list[WorkflowRun]) -> list[Finding]:
    """Where the failures are concentrated.

    Named separately from the workflow findings because the answer changes what you
    do: one workflow failing everywhere is a broken workflow, and every workflow
    failing on one branch is a broken branch.
    """
    findings = []
    for branch, group in _grouped(runs, lambda run: run.branch).items():
        failures = [run for run in group if _verdict(run) == "failed"]
        if len(group) < MIN_RUNS or not failures:
            continue

        rate = len(failures) / len(group) * 100
        if rate < CHRONIC_FAILURE_RATE:
            continue

        findings.append(
            Finding(
                kind="branch",
                subject=branch,
                detail=f"{_count(len(failures), 'failure', 'failures')} in {len(group)} runs",
                runs=len(group),
                failed=len(failures),
                last_seen_at=failures[0].started_at,
                run_url=failures[0].html_url,
            )
        )
    return findings


def _grouped(
    runs: list[WorkflowRun], key: Callable[[WorkflowRun], str | None]
) -> dict[str, list[WorkflowRun]]:
    """Runs gathered under a key, each list still newest-first. Rows with no key —
    a run with no branch recorded — are dropped rather than collected under a name
    that was never in the data."""
    groups: dict[str, list[WorkflowRun]] = defaultdict(list)
    for run in runs:
        value = key(run)
        if value is not None:
            groups[value].append(run)
    return groups


def _verdict(run: WorkflowRun) -> str:
    return "passed" if run.conclusion in SUCCEEDED else "failed"


def _mean(values: Iterable[int]) -> float:
    collected = list(values)
    return sum(collected) / len(collected)


def _minutes(seconds: float) -> str:
    if seconds < 60:
        return f"{round(seconds)}s"
    return f"{round(seconds / 60, 1)}m"


def _count(value: int, singular: str, plural: str) -> str:
    return f"{value} {singular if value == 1 else plural}"
