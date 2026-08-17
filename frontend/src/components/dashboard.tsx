"use client";

import { useMemo, useState } from "react";

import { ButtonLink } from "@/components/button";
import { LiveActivity } from "@/components/live-activity";
import { Notice } from "@/components/notice";
import { ProjectSheet } from "@/components/project-sheet";
import { Reading } from "@/components/reading";
import { RunFeed } from "@/components/run-feed";
import { Sheet, SheetHead } from "@/components/sheet";
import { StepWedge } from "@/components/status";
import { SyncLine } from "@/components/sync-line";
import { WindowControl, type WindowDays } from "@/components/window-control";
import { formatDuration, formatWhen } from "@/lib/outcome";
import {
  isAccessExpired,
  useActivityBoard,
  useOverview,
  useRecentDeployments,
  useRecentRuns,
  useSession,
} from "@/lib/queries";

const CONTROL_BAR_LENGTH = 12;
const RUN_FEED_LENGTH = 40;

export function Dashboard() {
  const session = useSession();
  const signedIn = Boolean(session.data);
  const [days, setDays] = useState<WindowDays>(30);

  const board = useActivityBoard(signedIn);
  const overview = useOverview(days, signedIn);
  const deployments = useRecentDeployments(100, signedIn);
  const runs = useRecentRuns(RUN_FEED_LENGTH, signedIn);

  const deploysByRepository = useMemo(
    () => groupByRepository(deployments.data ?? []),
    [deployments.data],
  );
  const runsByRepository = useMemo(() => groupByRepository(runs.data ?? []), [runs.data]);

  if (session.isPending || (signedIn && overview.isPending)) {
    return <PullingSheet />;
  }

  if (!signedIn) {
    return (
      <Sheet>
        <SheetHead title="Dashboard" />
        <Notice
          title="Sign in to see your projects"
          detail="The dashboard reads every Actions run collected for the repositories you connect, and the probe results for the endpoints they deploy to."
          action={
            <ButtonLink href="/api/auth/github" variant="primary">
              Sign in with GitHub
            </ButtonLink>
          }
        />
      </Sheet>
    );
  }

  if (overview.error) {
    return (
      <Sheet>
        <SheetHead title="Dashboard" />
        <Notice
          tone="problem"
          title="Could not read your metrics"
          detail={overview.error.message}
        />
      </Sheet>
    );
  }

  const data = overview.data;
  if (!data || data.connected_repositories === 0) {
    return (
      <Sheet>
        <SheetHead title="Dashboard" />
        <Notice
          title="No projects on press yet"
          detail="Connect a repository and DeployLens starts collecting its Actions runs straight away. Everything on this page is measured, so it stays empty until there is something to measure."
          action={
            <ButtonLink href="/repositories" variant="primary">
              Choose repositories
            </ButtonLink>
          }
        />
      </Sheet>
    );
  }

  const { delivery, pipeline, uptime, review } = data;
  const live = (board.data?.items ?? []).filter((item) => item.live);
  const window = `${days} d`;
  const quiet = pipeline.runs === 0 && pipeline.last_run_at !== null;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="flex flex-col gap-2">
          <h1 className="text-rank-b">Everything on press</h1>
          <p className="text-ink-quiet">
            {data.connected_repositories} project{data.connected_repositories === 1 ? "" : "s"}{" "}
            tracked · read over the last {days} days
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <SyncLine
            lastSyncedAt={board.data?.last_synced_at ?? null}
            failed={board.data?.failed ?? 0}
            expired={isAccessExpired(board.error)}
          />
          <WindowControl value={days} onChange={setDays} />
        </div>
      </div>

      {live.length > 0 ? <LiveActivity items={live} loading={false} compact /> : null}

      {quiet ? (
        <p className="label border-wait/50 bg-wait-quiet !text-wait border px-4 py-3 !tracking-[0.1em]">
          Nothing ran in this window — the newest run is {formatWhen(pipeline.last_run_at)}. Widen
          the window to read a project that has finished shipping.
        </p>
      ) : null}

      <Sheet>
        <SheetHead title="Across every project" meta={window} />
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
                : "no deploy workflow"
            }
            absent="none yet"
          />
          <Reading
            label="Uptime"
            value={uptime.uptime_percent}
            unit="%"
            sample={
              uptime.monitored_urls > 0
                ? `${uptime.monitored_urls} url${uptime.monitored_urls === 1 ? "" : "s"} · ${uptime.probes} read${uptime.probes === 1 ? "" : "s"}`
                : "set one on a project"
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
            label="Open now"
            value={review.open_now || null}
            sample="awaiting review"
            absent="none open"
          />
          <Reading
            label="Commits"
            value={review.commits || null}
            sample={`${review.commits_per_week}/wk · ${window}`}
            absent="none in window"
          />
        </div>
      </Sheet>

      <div className="grid [grid-template-columns:repeat(auto-fit,minmax(min(100%,26rem),1fr))] gap-8">
        {data.repositories.map((metrics) => (
          <ProjectSheet
            key={metrics.repository_id}
            metrics={metrics}
            latestDeploy={(deploysByRepository.get(metrics.repository_id) ?? [])[0] ?? null}
            runs={runsByRepository.get(metrics.repository_id) ?? []}
            windowDays={days}
          />
        ))}
      </div>

      <RunFeed runs={runs.data ?? []} loading={runs.isPending} showRepository />
    </div>
  );
}

function groupByRepository<T extends { repository_id: string }>(rows: T[]): Map<string, T[]> {
  const grouped = new Map<string, T[]>();
  for (const row of rows) {
    const list = grouped.get(row.repository_id) ?? [];
    if (list.length < CONTROL_BAR_LENGTH) {
      list.push(row);
      grouped.set(row.repository_id, list);
    }
  }
  return grouped;
}

function PullingSheet() {
  return (
    <Sheet>
      <SheetHead title="Dashboard" />
      <div className="flex flex-col gap-4 px-5 py-8" aria-busy="true">
        {[0, 1, 2].map((row) => (
          <span
            key={row}
            className="bg-rule h-3 animate-pulse rounded-[1px]"
            style={{ width: `${12 + row * 6}rem`, animationDelay: `${row * 120}ms` }}
          />
        ))}
      </div>
    </Sheet>
  );
}
