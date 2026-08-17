"use client";

import Link from "next/link";
import { useState } from "react";

import { ButtonLink } from "@/components/button";
import { LiveActivity } from "@/components/live-activity";
import { Notice } from "@/components/notice";
import { PullRequestList } from "@/components/pull-request-list";
import { Reading } from "@/components/reading";
import { RunFeed } from "@/components/run-feed";
import { Sheet, SheetHead } from "@/components/sheet";
import { SyncLine } from "@/components/sync-line";
import { ControlBar, OutcomeMark, SignOff, StepWedge, type Outcome } from "@/components/status";
import { WindowControl, type WindowDays } from "@/components/window-control";
import { ApiError } from "@/lib/api";
import { formatDuration, formatHours, formatWhen, outcomeOf, runOutcome } from "@/lib/outcome";
import {
  useActivityBoard,
  useRecentDeployments,
  useRecentRuns,
  usePullRequests,
  useRepositoryDetail,
  useSession,
} from "@/lib/queries";
import type { DeploymentSummary, RunGroup } from "@/lib/types";

const RUN_FEED_LENGTH = 60;
const CONTROL_BAR_LENGTH = 24;
const DEPLOY_LIST_LENGTH = 12;
const PULL_REQUEST_LENGTH = 40;

/**
 * One project, on its own. The dashboard answers "how is everything"; a
 * developer standing in front of a single repository is asking something
 * narrower — which workflow keeps failing, on which branch, and where the last
 * deploy went — and those breakdowns are meaningless averaged across projects.
 */
export function ProjectDetail({ repositoryId }: { repositoryId: string }) {
  const session = useSession();
  const signedIn = Boolean(session.data);
  const [days, setDays] = useState<WindowDays>(30);

  // The same board the dashboard and the live page watch, filtered to this project.
  // One loop serves every open page, and pulling for it refreshes the readings below.
  const board = useActivityBoard(signedIn);
  const detail = useRepositoryDetail(repositoryId, days, signedIn);
  const runs = useRecentRuns(RUN_FEED_LENGTH, signedIn, repositoryId);
  const deploys = useRecentDeployments(DEPLOY_LIST_LENGTH, signedIn, repositoryId);
  const pullRequests = usePullRequests(PULL_REQUEST_LENGTH, signedIn, repositoryId);
  const activity = (board.data?.items ?? []).filter((item) => item.repository_id === repositoryId);

  if (session.isPending || (signedIn && detail.isPending)) {
    return <PullingSheet />;
  }

  if (!signedIn) {
    return (
      <Sheet>
        <SheetHead title="Project" />
        <Notice
          title="Sign in to read this project"
          detail="Projects are read from the repositories connected to your GitHub account."
          action={
            <ButtonLink href="/api/auth/github" variant="primary">
              Sign in with GitHub
            </ButtonLink>
          }
        />
      </Sheet>
    );
  }

  if (detail.error) {
    const missing = detail.error instanceof ApiError && detail.error.status === 404;
    return (
      <Sheet>
        <SheetHead title="Project" />
        <Notice
          tone={missing ? "quiet" : "problem"}
          title={missing ? "No such project" : "Could not read this project"}
          detail={
            missing
              ? "It is not connected to your account, or it was disconnected — disconnecting takes the collected history with it."
              : detail.error.message
          }
          action={
            <ButtonLink href="/dashboard" variant="secondary">
              Back to every project
            </ButtonLink>
          }
        />
      </Sheet>
    );
  }

  const data = detail.data;
  if (!data) return null;

  const { repository, delivery, pipeline, uptime, review } = data;
  const window = `${days} d`;
  const outcomes: Outcome[] = (runs.data ?? [])
    .slice(0, CONTROL_BAR_LENGTH)
    .map((run) => runOutcome(run.status, run.conclusion));

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-5">
        <Link href="/dashboard" className="label hover:!text-ink w-fit transition-colors">
          ← Every project
        </Link>

        <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
          <div className="flex min-w-0 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <h1 className="text-rank-b truncate">{repository.full_name}</h1>
              <SignOff outcome={outcomes[0] ?? "none"} />
            </div>
            <p className="label !tracking-[0.08em]">
              {repository.default_branch} · connected {formatWhen(repository.connected_at)} ·{" "}
              {earliest(data.first_activity_at, review.first_commit_week)
                ? `history back to ${formatDate(earliest(data.first_activity_at, review.first_commit_week)!)}`
                : "no history collected"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <SyncLine
              lastSyncedAt={board.data?.last_synced_at ?? null}
              failed={board.data?.failed ?? 0}
            />
            <ButtonLink
              href={repository.github_url}
              target="_blank"
              rel="noreferrer"
              variant="secondary"
              size="compact"
            >
              Open on GitHub
            </ButtonLink>
            <WindowControl value={days} onChange={setDays} />
          </div>
        </div>
      </div>

      {activity.length > 0 ? (
        <LiveActivity items={activity} loading={false} title="Happening now" />
      ) : null}

      <Sheet>
        <SheetHead title="This project" meta={window} />
        <div className="grid gap-x-8 gap-y-7 px-5 py-6 sm:grid-cols-2 lg:grid-cols-6">
          <div className="flex flex-col gap-3 sm:col-span-2 lg:col-span-1">
            <Reading
              label="Health score"
              value={data.health_score}
              sample={window}
              absent="nothing measured"
            />
            <StepWedge value={data.health_score} steps={8} />
          </div>
          <Reading
            label="Runs"
            value={pipeline.runs || null}
            sample={`${pipeline.workflows} workflow${pipeline.workflows === 1 ? "" : "s"} · ${pipeline.branches} branch${pipeline.branches === 1 ? "" : "es"}`}
            absent="nothing run"
          />
          <Reading
            label="Runs passing"
            value={pipeline.success_rate}
            unit="%"
            sample={`${pipeline.succeeded} of ${pipeline.succeeded + pipeline.failed} decided`}
            absent="no decided runs"
          />
          <Reading
            label="Deploys"
            value={delivery.deployments || null}
            sample={
              delivery.last_deployment_at
                ? `${delivery.deployments_per_week}/wk · last ${formatWhen(delivery.last_deployment_at)}`
                : "no deploy recorded"
            }
            absent="none yet"
          />
          <Reading
            label="Uptime"
            value={uptime.uptime_percent}
            unit="%"
            sample={
              uptime.monitored_urls > 0
                ? `${uptime.probes} probes · ${uptime.average_response_time_ms ?? "—"} ms`
                : "no endpoint monitored"
            }
            absent="not monitored"
          />
          <Reading
            label="Average run"
            value={formatDuration(pipeline.average_duration_seconds)}
            sample={`${window} · ${pipeline.runs} runs`}
            absent="not timed"
          />
        </div>

        <div className="border-rule grid gap-x-8 gap-y-7 border-t px-5 py-6 sm:grid-cols-2 lg:grid-cols-4">
          <Reading
            label="Merged"
            value={review.merged || null}
            sample={review.opened ? `${review.opened} opened in window` : "none opened"}
            absent="none merged"
          />
          <Reading
            label="Merge rate"
            value={review.merge_rate}
            unit="%"
            sample={`${review.merged} of ${review.merged + review.closed_unmerged} decided`}
            absent="nothing decided"
          />
          <Reading
            label="Time to merge"
            value={formatHours(review.median_hours_to_merge)}
            sample="median"
            absent="nothing merged"
          />
          <Reading
            label="Commits"
            value={review.commits || null}
            sample={`${review.commits_per_week}/wk · ${window}`}
            absent="none in window"
          />
        </div>

        {outcomes.length > 0 ? (
          <div className="border-rule flex flex-col gap-2 border-t px-5 py-5">
            <span className="label">Last {outcomes.length} runs · newest first</span>
            <ControlBar outcomes={outcomes} />
          </div>
        ) : null}
      </Sheet>

      <div className="grid gap-8 lg:grid-cols-2">
        <GroupSheet
          title="By workflow"
          groups={data.workflows}
          empty="No workflows have run in this window."
        />
        <GroupSheet
          title="By branch"
          groups={data.branches}
          empty="No branch has run anything in this window."
        />
      </div>

      <Deploys
        deployments={deploys.data ?? []}
        loading={deploys.isPending}
        defaultBranch={repository.default_branch}
      />

      <PullRequestList pullRequests={pullRequests.data ?? []} loading={pullRequests.isPending} />

      <RunFeed
        runs={runs.data ?? []}
        loading={runs.isPending}
        title="Every run"
        offerDeployFilter={false}
      />
    </div>
  );
}

/**
 * Which workflow, or which branch, is costing the most. Sorted by volume from
 * the API, so the row that leads is the one that runs most — the failures
 * underneath it are then read against a sample worth trusting.
 */
function GroupSheet({
  title,
  groups,
  empty,
}: {
  title: string;
  groups: RunGroup[];
  empty: string;
}) {
  return (
    <Sheet>
      <SheetHead title={title} meta={groups.length > 0 ? `${groups.length}` : undefined} />
      {groups.length === 0 ? (
        <Notice title={empty} />
      ) : (
        <ul>
          {groups.map((group) => (
            <li
              key={group.name}
              className="border-rule grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-1 border-b px-5 py-3 last:border-b-0"
            >
              <span className="text-ink truncate">{group.name}</span>
              <span className="text-ink text-rank-c font-sans" data-numeric>
                {group.success_rate === null ? "—" : `${group.success_rate}%`}
              </span>
              <span className="label !tracking-[0.08em]">
                {group.runs} run{group.runs === 1 ? "" : "s"}
                {group.failed > 0 ? ` · ${group.failed} failed` : ""}
                {group.average_duration_seconds
                  ? ` · ${formatDuration(group.average_duration_seconds)} avg`
                  : ""}
              </span>
              <span className="label text-right !tracking-[0.08em]">
                {formatWhen(group.last_run_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}

/**
 * Deploys carry the one thing no other row has: the address the build actually
 * went to. A provider deploy with no workflow behind it still belongs here.
 */
function Deploys({
  deployments,
  loading,
  defaultBranch,
}: {
  deployments: DeploymentSummary[];
  loading: boolean;
  defaultBranch: string;
}) {
  return (
    <Sheet>
      <SheetHead
        title="Deploys"
        meta={deployments.length > 0 ? `${deployments.length}` : undefined}
      />
      {loading ? (
        <div className="px-5 py-8" aria-busy="true">
          <span className="bg-rule block h-3 w-40 animate-pulse rounded-[1px]" />
        </div>
      ) : deployments.length === 0 ? (
        <Notice
          title="No deploys recorded"
          detail={`Deploys are read from GitHub — both from a workflow that ships ${defaultBranch} and from a hosting provider that records its own. Neither has reported one in this project yet.`}
        />
      ) : (
        <ul>
          {deployments.map((deploy) => {
            const outcome = outcomeOf(deploy.status);
            return (
              <li
                key={deploy.id}
                className="border-rule grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 border-b px-5 py-3 last:border-b-0 sm:grid-cols-[auto_minmax(0,10rem)_minmax(0,1fr)_auto]"
              >
                <OutcomeMark outcome={outcome} className={toneOf(outcome)} />
                <span className="text-ink truncate">{deploy.environment}</span>
                {deploy.deployment_url ? (
                  <a
                    href={deploy.deployment_url}
                    target="_blank"
                    rel="noreferrer"
                    className="label !text-accent decoration-accent/40 hover:decoration-accent col-span-2 truncate !tracking-[0.08em] underline underline-offset-[3px] transition-colors sm:col-span-1"
                  >
                    {stripScheme(deploy.deployment_url)} ↗
                  </a>
                ) : (
                  <span className="label col-span-2 truncate !tracking-[0.08em] sm:col-span-1">
                    {deploy.branch ?? "no branch"}
                    {deploy.commit_sha ? ` · ${deploy.commit_sha.slice(0, 7)}` : ""}
                  </span>
                )}
                <span className="label text-right !tracking-[0.08em]">
                  {took(deploy.duration_seconds) ?? deploy.status} · {formatWhen(deploy.started_at)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Sheet>
  );
}

/**
 * A provider deploy is recorded as a single event, so its duration is zero
 * rather than unknown. Printing "0s" claims a build that took no time; the
 * outcome word is the honest thing to show instead.
 */
function took(seconds: number | null): string | null {
  return seconds ? formatDuration(seconds) : null;
}

function stripScheme(url: string): string {
  return url.replace(/^https?:\/\//, "");
}

function toneOf(outcome: Outcome): string {
  if (outcome === "ok") return "text-ok";
  if (outcome === "hold") return "text-hold";
  if (outcome === "wait") return "text-wait";
  return "text-ink-faint";
}

/**
 * How far back the page can actually see. Runs and commits reach back different
 * distances - GitHub keeps a year of commit totals but expires old run logs - so
 * the honest answer is whichever reaches further.
 */
function earliest(runFrom: string | null, commitsFrom: string | null): string | null {
  if (!runFrom) return commitsFrom;
  if (!commitsFrom) return runFrom;
  return new Date(commitsFrom) < new Date(runFrom) ? commitsFrom : runFrom;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function PullingSheet() {
  return (
    <Sheet>
      <SheetHead title="Project" />
      <div className="flex flex-col gap-4 px-5 py-8" aria-busy="true">
        {[0, 1, 2].map((row) => (
          <span
            key={row}
            className="bg-rule h-3 animate-pulse rounded-[1px]"
            style={{ width: `${14 + row * 5}rem`, animationDelay: `${row * 120}ms` }}
          />
        ))}
      </div>
    </Sheet>
  );
}
