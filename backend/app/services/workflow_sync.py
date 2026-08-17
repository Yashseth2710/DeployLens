import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.workflow import Deployment, WorkflowRun
from app.services import github_api
from app.services.github_api import GitHubDeployment, GitHubWorkflowRun

# A repository's runs are mostly tests and linting. Only the ones whose workflow is
# named for shipping count as deployments, so reliability metrics measure releases
# rather than every push.
DEPLOY_WORKFLOW = re.compile(r"deploy|release|publish|ship|promote", re.IGNORECASE)

FIRST_SYNC_PAGES = 3
REFRESH_PAGES = 1


@dataclass(frozen=True)
class SyncResult:
    runs_seen: int
    runs_added: int
    deployments_added: int
    provider_deployments: int


def sync_repository(db: Session, repository: Repository, access_token: str) -> SyncResult:
    """A first sync reaches back further than a refresh: the dashboard needs history to
    plot on day one, but after that only the newest page can hold anything unseen."""
    known = db.scalar(
        select(WorkflowRun.id).where(WorkflowRun.repository_id == repository.id).limit(1)
    )
    pages = REFRESH_PAGES if known else FIRST_SYNC_PAGES

    runs = github_api.list_workflow_runs(access_token, repository.full_name, pages=pages)
    result = record_runs(db, repository, runs)

    # Most projects deploy through a provider integration rather than a workflow, so
    # the runs above never mention the thing that actually shipped. GitHub records
    # those deployments regardless of who created them.
    provider = record_provider_deployments(
        db,
        repository,
        github_api.list_deployments(
            access_token, repository.full_name, settled_ids=_settled_deployment_ids(db, repository)
        ),
    )
    return SyncResult(
        runs_seen=result.runs_seen,
        runs_added=result.runs_added,
        deployments_added=result.deployments_added,
        provider_deployments=provider,
    )


# A deployment that succeeded or failed is finished with. Re-reading its status every
# pass is what turned one repository into thirty one requests a sync.
SETTLED_DEPLOY_STATES = ("success", "failure", "error", "inactive")


def _settled_deployment_ids(db: Session, repository: Repository) -> frozenset[int]:
    return frozenset(
        db.scalars(
            select(Deployment.github_deployment_id).where(
                Deployment.repository_id == repository.id,
                Deployment.github_deployment_id.is_not(None),
                Deployment.status.in_(SETTLED_DEPLOY_STATES),
            )
        )
    )


def record_provider_deployments(
    db: Session, repository: Repository, deployments: list[GitHubDeployment]
) -> int:
    """Keyed on GitHub's deployment id, so a redeploy of the same commit is its own
    row and a resync updates rather than duplicates."""
    if not deployments:
        return 0

    for deployment in deployments:
        values = {
            "repository_id": repository.id,
            "github_deployment_id": deployment.github_deployment_id,
            "environment": deployment.environment[:50],
            "status": deployment.state,
            "branch": deployment.ref,
            "commit_sha": deployment.commit_sha,
            "author": deployment.creator,
            "started_at": deployment.created_at,
            "completed_at": deployment.updated_at,
            "duration_seconds": duration_of(deployment.created_at, deployment.updated_at),
            "deployment_url": deployment.deployment_url,
        }
        db.execute(
            insert(Deployment)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_deployments_repo_github_id",
                set_={
                    key: values[key]
                    for key in ("status", "completed_at", "duration_seconds", "deployment_url")
                },
            )
        )
    db.commit()
    return len(deployments)


def record_runs(db: Session, repository: Repository, runs: list[GitHubWorkflowRun]) -> SyncResult:
    if not runs:
        return SyncResult(runs_seen=0, runs_added=0, deployments_added=0, provider_deployments=0)

    before = _counts(db, repository.id)
    for run in runs:
        run_id = _upsert_run(db, repository, run)
        if is_deployment(run):
            _upsert_deployment(db, repository, run, run_id)
    db.commit()
    after = _counts(db, repository.id)

    return SyncResult(
        runs_seen=len(runs),
        runs_added=after[0] - before[0],
        deployments_added=after[1] - before[1],
        provider_deployments=0,
    )


def is_deployment(run: GitHubWorkflowRun) -> bool:
    return run.event == "deployment" or bool(DEPLOY_WORKFLOW.search(run.workflow_name))


def _upsert_run(db: Session, repository: Repository, run: GitHubWorkflowRun) -> UUID:
    """Keyed on the GitHub run id, so a re-sync and a redelivered webhook both land on
    the row that is already there instead of a duplicate."""
    values = {
        "repository_id": repository.id,
        "github_run_id": run.github_run_id,
        "workflow_name": run.workflow_name,
        "branch": run.branch,
        "commit_sha": run.commit_sha,
        "status": run.status,
        "conclusion": run.conclusion,
        "event": run.event,
        "actor": run.actor,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "duration_seconds": duration_of(run.started_at, run.completed_at),
        "html_url": run.html_url,
    }
    statement = (
        insert(WorkflowRun)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_workflow_runs_repo_run",
            set_={
                # event and actor are refreshed too, so a resync backfills rows that
                # were ingested before those columns existed.
                key: values[key]
                for key in (
                    "status",
                    "conclusion",
                    "completed_at",
                    "duration_seconds",
                    "event",
                    "actor",
                )
            },
        )
        .returning(WorkflowRun.id)
    )
    return db.execute(statement).scalar_one()


def _upsert_deployment(
    db: Session, repository: Repository, run: GitHubWorkflowRun, run_id: UUID
) -> None:
    environment = (
        "production" if run.branch == repository.default_branch else run.branch or "preview"
    )
    values = {
        "repository_id": repository.id,
        "workflow_run_id": run_id,
        "environment": environment[:50],
        "status": run.conclusion or run.status,
        "branch": run.branch,
        "commit_sha": run.commit_sha,
        "author": run.actor,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "duration_seconds": duration_of(run.started_at, run.completed_at),
    }
    statement = (
        insert(Deployment)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["workflow_run_id"],
            set_={
                key: values[key]
                for key in ("status", "completed_at", "duration_seconds", "environment")
            },
        )
    )
    db.execute(statement)


def duration_of(started_at: datetime | None, completed_at: datetime | None) -> int | None:
    if started_at is None or completed_at is None:
        return None
    seconds = int((completed_at - started_at).total_seconds())
    # A clock skew between GitHub's two timestamps should not produce a negative average.
    return max(seconds, 0)


def _counts(db: Session, repository_id: UUID) -> tuple[int, int]:
    runs = db.scalar(
        select(func.count(WorkflowRun.id)).where(WorkflowRun.repository_id == repository_id)
    )
    deployments = db.scalar(
        select(func.count(Deployment.id)).where(Deployment.repository_id == repository_id)
    )
    return runs or 0, deployments or 0
