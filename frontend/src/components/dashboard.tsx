"use client";

import { useMemo, useState } from "react";

import { ButtonLink } from "@/components/button";
import { Notice } from "@/components/notice";
import { ProjectSheet } from "@/components/project-sheet";
import { Reading } from "@/components/reading";
import { Sheet, SheetHead } from "@/components/sheet";
import { OutcomeMark, StepWedge } from "@/components/status";
import { WindowControl, type WindowDays } from "@/components/window-control";
import { cn } from "@/lib/cn";
import { EVENT_LABEL, formatDuration, formatWhen, runOutcome } from "@/lib/outcome";
import { useOverview, useRecentDeployments, useRecentRuns, useSession } from "@/lib/queries";
import type { WorkflowRunRow } from "@/lib/types";

const CONTROL_BAR_LENGTH = 12;
const RUN_FEED_LENGTH = 40;

type RunFilter = "all" | "failed" | "deploys";

export function Dashboard() {
  const session = useSession();
  const signedIn = Boolean(session.data);
  const [days, setDays] = useState<WindowDays>(30);

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

  const { delivery, pipeline, uptime } = data;
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
        <WindowControl value={days} onChange={setDays} />
      </div>

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
                ? `${uptime.monitored_urls} url${uptime.monitored_urls === 1 ? "" : "s"} · ${uptime.probes} probes`
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

      <Activity runs={runs.data ?? []} loading={runs.isPending} />
    </div>
  );
}

/**
 * Every run, not only the ones that shipped. A failing test on a pull request is
 * the question a developer asks most often, and it would never appear in a feed
 * built only from deployments.
 */
function Activity({ runs, loading }: { runs: WorkflowRunRow[]; loading: boolean }) {
  const [filter, setFilter] = useState<RunFilter>("all");

  const shown = runs.filter((run) => {
    if (filter === "failed") return runOutcome(run.status, run.conclusion) === "hold";
    if (filter === "deploys") return /deploy|release|publish|ship|promote/i.test(run.workflow_name);
    return true;
  });

  return (
    <Sheet>
      <SheetHead
        title="Pipeline activity"
        meta={`${shown.length} of ${runs.length} runs`}
        action={
          <div
            className="border-rule flex items-center border"
            role="group"
            aria-label="Filter runs"
          >
            {(["all", "failed", "deploys"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setFilter(option)}
                aria-pressed={option === filter}
                className={cn(
                  "label border-rule px-3 py-1.5 !tracking-[0.12em] transition-colors not-last:border-r",
                  option === filter
                    ? "bg-accent !text-accent-ink"
                    : "hover:bg-sheet-raised hover:!text-ink",
                )}
              >
                {option}
              </button>
            ))}
          </div>
        }
      />

      {loading ? (
        <div className="px-5 py-8" aria-busy="true">
          <span className="bg-rule block h-3 w-48 animate-pulse rounded-[1px]" />
        </div>
      ) : shown.length === 0 ? (
        <Notice
          title={filter === "all" ? "No runs recorded yet" : `No ${filter} runs recorded`}
          detail={
            filter === "all"
              ? "Runs arrive within seconds of a workflow finishing, or after a sync from the repositories page."
              : "Change the filter to see the rest of the pipeline."
          }
        />
      ) : (
        <ul>
          {shown.map((run) => {
            const outcome = runOutcome(run.status, run.conclusion);
            return (
              <li
                key={run.id}
                className="border-rule hover:bg-sheet-raised grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 border-b px-5 py-3 transition-colors last:border-b-0 sm:grid-cols-[auto_minmax(0,13rem)_minmax(0,1fr)_auto]"
              >
                <OutcomeMark outcome={outcome} className={toneOf(outcome)} />
                <a
                  href={run.html_url ?? undefined}
                  target="_blank"
                  rel="noreferrer"
                  className="text-ink hover:text-accent truncate transition-colors"
                >
                  {run.workflow_name}
                </a>
                <span className="label col-span-2 truncate !tracking-[0.08em] sm:col-span-1">
                  {run.branch ?? "no branch"}
                  {run.event ? ` · ${EVENT_LABEL[run.event] ?? run.event}` : ""}
                  {run.commit_sha ? ` · ${run.commit_sha.slice(0, 7)}` : ""}
                </span>
                <span className="label text-right !tracking-[0.08em]">
                  {formatDuration(run.duration_seconds) ?? "—"} · {formatWhen(run.started_at)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Sheet>
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

function toneOf(outcome: ReturnType<typeof runOutcome>): string {
  if (outcome === "ok") return "text-ok";
  if (outcome === "hold") return "text-hold";
  if (outcome === "wait") return "text-wait";
  return "text-ink-faint";
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
