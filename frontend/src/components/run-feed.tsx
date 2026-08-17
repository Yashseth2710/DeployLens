"use client";

import { useState } from "react";

import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { OutcomeMark } from "@/components/status";
import { cn } from "@/lib/cn";
import { EVENT_LABEL, formatDuration, formatWhen, runOutcome } from "@/lib/outcome";
import type { WorkflowRunRow } from "@/lib/types";

const DEPLOY_WORKFLOW = /deploy|release|publish|ship|promote/i;

type RunFilter = "all" | "failed" | "deploys";

/**
 * Every run, not only the ones that shipped. A failing test on a pull request is
 * the question a developer asks most often, and it would never appear in a feed
 * built only from deployments.
 *
 * The dashboard shows this across every project and the detail page shows one
 * project's own; the difference is which runs are handed in, not how they read.
 */
export function RunFeed({
  runs,
  loading,
  title = "Pipeline activity",
  showRepository = false,
  offerDeployFilter = true,
}: {
  runs: WorkflowRunRow[];
  loading: boolean;
  title?: string;
  showRepository?: boolean;
  /** Off where a deploys panel already answers this better, and answers it for
   * provider deploys too — filtering runs by workflow name finds nothing on a
   * project that ships through Vercel rather than through Actions. */
  offerDeployFilter?: boolean;
}) {
  const [filter, setFilter] = useState<RunFilter>("all");
  const filters = offerDeployFilter
    ? (["all", "failed", "deploys"] as const)
    : (["all", "failed"] as const);

  const shown = runs.filter((run) => {
    if (filter === "failed") return runOutcome(run.status, run.conclusion) === "hold";
    if (filter === "deploys") return DEPLOY_WORKFLOW.test(run.workflow_name);
    return true;
  });

  return (
    <Sheet>
      <SheetHead
        title={title}
        meta={`${shown.length} of ${runs.length} runs`}
        action={
          <div
            className="border-rule flex items-center border"
            role="group"
            aria-label="Filter runs"
          >
            {filters.map((option) => (
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
          title={
            filter === "all"
              ? "No runs recorded yet"
              : filter === "deploys"
                ? "No deploy workflow here"
                : "No failed runs recorded"
          }
          detail={
            filter === "all"
              ? "Runs arrive within seconds of a workflow finishing, or after a sync from the repositories page."
              : filter === "deploys"
                ? "This filter reads workflow names, so it only finds projects that ship through Actions. A project deployed by a hosting provider records its deploys separately — they are on its own page, with the address each build went to."
                : "Nothing failed in this window. Change the filter to see the rest of the pipeline."
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
                  {showRepository ? `${run.repository_full_name} · ` : ""}
                  {run.workflow_name}
                </a>
                <span className="label col-span-2 truncate !tracking-[0.08em] sm:col-span-1">
                  {run.branch ?? "no branch"}
                  {run.event ? ` · ${EVENT_LABEL[run.event] ?? run.event}` : ""}
                  {run.actor ? ` · ${run.actor}` : ""}
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

function toneOf(outcome: ReturnType<typeof runOutcome>): string {
  if (outcome === "ok") return "text-ok";
  if (outcome === "hold") return "text-hold";
  if (outcome === "wait") return "text-wait";
  return "text-ink-faint";
}
