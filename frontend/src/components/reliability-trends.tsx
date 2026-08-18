"use client";

import { useState } from "react";

import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { TrendChart, type Plot } from "@/components/trend-chart";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/outcome";
import type { Trends } from "@/lib/types";

type Series = "runs" | "deploys" | "uptime";

const SERIES: { id: Series; label: string }[] = [
  { id: "runs", label: "runs" },
  { id: "deploys", label: "deploys" },
  { id: "uptime", label: "uptime" },
];

/**
 * The readings above this sheet say what the numbers are now. This says how they got
 * there — the same measurements plotted a day at a time.
 *
 * Three series rather than one chart each, because they answer at wildly different
 * densities: a project runs CI many times a day, deploys weekly, and is probed hourly
 * only once an endpoint has been named. Stacking three charts would give two of them
 * a page of empty axis, so they share one plane and one control.
 */
export function ReliabilityTrends({
  trends,
  loading,
  windowDays,
}: {
  trends: Trends | undefined;
  loading: boolean;
  windowDays: number;
}) {
  const [series, setSeries] = useState<Series>("runs");

  if (loading) {
    return (
      <Sheet>
        <SheetHead title="How it got here" />
        <div className="px-5 py-8" aria-busy="true">
          <span className="bg-rule block h-3 w-44 animate-pulse rounded-[1px]" />
        </div>
      </Sheet>
    );
  }

  const plots = trends ? plotsFor(series, trends) : [];
  const recorded = trends ? recordedDays(trends) : 0;
  // Counts the series on screen, not the union of all three: a meta that said ten
  // while the visible chart held four would be describing something else.
  const plotted = plots.length;

  return (
    <Sheet>
      <SheetHead
        title="How it got here"
        meta={plotted > 0 ? `${plotted} day${plotted === 1 ? "" : "s"} plotted` : undefined}
        action={
          <div className="border-rule flex items-center border" role="group" aria-label="Series">
            {SERIES.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => setSeries(option.id)}
                aria-pressed={option.id === series}
                className={cn(
                  "label border-rule px-3 py-1.5 !tracking-[0.12em] transition-colors not-last:border-r",
                  option.id === series
                    ? "bg-accent !text-accent-ink"
                    : "hover:bg-sheet-raised hover:!text-ink",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        }
      />

      {recorded === 0 ? (
        <Notice
          title="Nothing plotted yet"
          detail="Days are plotted as they are collected. A run, a deploy, or an endpoint read all put a mark on this chart — the first arrives within seconds of a workflow finishing."
        />
      ) : (
        <TrendChart
          points={plots}
          windowDays={windowDays}
          unit={unitFor(series)}
          tone={series === "uptime" ? "ok" : "accent"}
          emptyLabel={emptyFor(series)}
        />
      )}
    </Sheet>
  );
}

/**
 * Each series carries its own sentence, because the same column means a different
 * thing in each: a failed run is a red build, a failed deploy is a release that did
 * not ship, and a down read is the site not answering.
 */
function plotsFor(series: Series, trends: Trends): Plot[] {
  if (series === "runs") {
    return trends.runs.map((point) => ({
      day: point.day,
      total: point.runs,
      failed: point.failed,
      detail: [
        `${point.runs} run${point.runs === 1 ? "" : "s"}`,
        point.failed > 0 ? `${point.failed} failed` : null,
        formatDuration(point.average_duration_seconds)
          ? `${formatDuration(point.average_duration_seconds)} avg`
          : null,
      ]
        .filter(Boolean)
        .join(" · "),
    }));
  }

  if (series === "deploys") {
    return trends.deployments.map((point) => ({
      day: point.day,
      total: point.deployments,
      failed: point.failed,
      detail: [
        `${point.deployments} deploy${point.deployments === 1 ? "" : "s"}`,
        point.failed > 0 ? `${point.failed} failed` : null,
        // A provider deploy is one event, so it records no duration. Printing "0s"
        // would claim a build that took no time.
        formatDuration(point.average_duration_seconds)
          ? `${formatDuration(point.average_duration_seconds)} avg`
          : null,
      ]
        .filter(Boolean)
        .join(" · "),
    }));
  }

  return trends.uptime.map((point) => ({
    day: point.day,
    total: point.probes,
    failed: point.probes - point.up,
    detail: [
      `${point.probes} read${point.probes === 1 ? "" : "s"}`,
      `${point.uptime_percent}% up`,
      point.probes - point.up > 0 ? `${point.probes - point.up} down` : null,
    ]
      .filter(Boolean)
      .join(" · "),
  }));
}

function recordedDays(trends: Trends): number {
  return new Set([
    ...trends.runs.map((point) => point.day),
    ...trends.deployments.map((point) => point.day),
    ...trends.uptime.map((point) => point.day),
  ]).size;
}

function unitFor(series: Series): string {
  if (series === "deploys") return "deploys";
  if (series === "uptime") return "reads";
  return "runs";
}

function emptyFor(series: Series): string {
  if (series === "deploys") {
    return "No deploy recorded in this window. Deploys are read from a workflow that ships, and from a hosting provider that records its own.";
  }
  if (series === "uptime") {
    return "No endpoint read in this window. Name one on a project page and it is probed within seconds.";
  }
  return "No run recorded in this window.";
}
