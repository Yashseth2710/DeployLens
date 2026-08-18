"use client";

import { useId, useMemo, useState } from "react";

import { cn } from "@/lib/cn";

/**
 * A day of something, plotted. `total` draws the column, `failed` fills the part of
 * it that went wrong, and `absent` days are the ones the API never returned.
 */
export type Plot = {
  day: string;
  total: number;
  failed: number;
  /** The line under the column, e.g. "31 runs · 3 failed · 2:03 avg". */
  detail: string;
};

const PLOT_HEIGHT = 128;
const MIN_COLUMN = 2;

// A column stops widening past this. Ten days across a desktop measure would otherwise
// draw ten slabs half a hand wide, which reads as a block of colour rather than as a
// series; the plot stays left-aligned and lets the rest of the row be empty axis.
const MAX_COLUMN_PX = 28;

// A plot narrower than its own date label has the axis hanging off the end of it, so
// a chart holding one or two days still reserves a readable measure.
const MIN_PLOT_PX = 140;

// Below this many days the plot is mostly empty ground, and a four-day series drawn at
// the ten-day column width is three marks adrift in a wide sheet. Short series spend the
// spare measure on wider columns instead, so the chart fills the space it was given.
const SPARSE_DAYS = 8;
const SPARSE_COLUMN_PX = 72;

/**
 * A day chart drawn as ruled columns on a continuous date axis.
 *
 * The axis is every day in the window, not every day that had data. A project that
 * ships twice in a month must read as two marks with silence around them rather than
 * as a line sloping between them, because the days in between are days nobody
 * deployed, not days a deploy took some interpolated value.
 *
 * Failures are drawn as a darker segment inside the column rather than as a second
 * series, so the height is always the total and the eye never has to add two bars
 * together to learn how much ran.
 */
export function TrendChart({
  points,
  windowDays,
  unit,
  emptyLabel,
  tone = "accent",
}: {
  points: Plot[];
  windowDays: number;
  /** Plural noun for the peak label: "runs", "deploys", "reads". */
  unit: string;
  emptyLabel: string;
  tone?: "accent" | "ok";
}) {
  const titleId = useId();
  const [reading, setReading] = useState<Plot | null>(null);

  const days = useMemo(() => spanDays(points, windowDays), [points, windowDays]);
  const peak = useMemo(() => Math.max(1, ...points.map((point) => point.total)), [points]);

  if (points.length === 0) {
    return (
      <div className="flex flex-col gap-2 px-5 py-8">
        <span className="text-ink-faint font-sans italic">{emptyLabel}</span>
      </div>
    );
  }

  const shown = reading ?? points[points.length - 1];
  const columnPx = days.length < SPARSE_DAYS ? SPARSE_COLUMN_PX : MAX_COLUMN_PX;

  return (
    <div className="flex flex-col gap-3 px-5 py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <span className="label !text-ink !tracking-[0.1em]">
          {shown.day === points[points.length - 1].day && !reading ? "Latest" : dayLabel(shown.day)}
          {" · "}
          <span className="!text-ink-quiet">{shown.detail}</span>
        </span>
        <span className="label !tracking-[0.1em]">
          peak {peak} {unit} · {windowDays} d
        </span>
      </div>

      <div
        className="flex flex-col gap-2"
        style={{ maxWidth: Math.max(MIN_PLOT_PX, days.length * (columnPx + 1)) }}
        onMouseLeave={() => setReading(null)}
      >
        <div
          role="img"
          aria-labelledby={titleId}
          className="flex items-end gap-px"
          style={{ height: PLOT_HEIGHT }}
        >
          {days.map(({ day, point }) => (
            <Column
              key={day}
              day={day}
              point={point}
              peak={peak}
              tone={tone}
              widthPx={columnPx}
              active={reading?.day === day}
              onEnter={() => setReading(point)}
            />
          ))}
        </div>

        {/* One day of data has one date, and printing it at both ends of a column-wide
            row sets the same label twice over itself. */}
        <div className="label flex justify-between gap-4 !tracking-[0.1em] whitespace-nowrap">
          <span>{dayLabel(days[0].day)}</span>
          {days.length > 1 ? <span>{dayLabel(days[days.length - 1].day)}</span> : null}
        </div>
      </div>

      <p id={titleId} className="sr-only">
        {points.length} day{points.length === 1 ? "" : "s"} with activity across the last{" "}
        {windowDays} days. Peak {peak} {unit}.{" "}
        {points.map((point) => `${dayLabel(point.day)}: ${point.detail}.`).join(" ")}
      </p>
    </div>
  );
}

/**
 * One day. A day with no data draws a hairline on the baseline rather than nothing at
 * all — the rule is what makes the gap visible as a gap instead of as the chart
 * simply ending.
 */
function Column({
  day,
  point,
  peak,
  tone,
  widthPx,
  active,
  onEnter,
}: {
  day: string;
  point: Plot | null;
  peak: number;
  tone: "accent" | "ok";
  widthPx: number;
  active: boolean;
  onEnter: () => void;
}) {
  if (!point) {
    return (
      <span
        className="bg-rule/60 min-w-px flex-1 self-end"
        style={{ height: 1, maxWidth: widthPx }}
        aria-hidden="true"
        title={`${dayLabel(day)} · nothing recorded`}
      />
    );
  }

  const height = Math.max(MIN_COLUMN, Math.round((point.total / peak) * PLOT_HEIGHT));
  const failedHeight = point.failed > 0 ? Math.max(1, (point.failed / point.total) * height) : 0;

  return (
    <span
      className="group relative min-w-px flex-1 self-end"
      style={{ height, maxWidth: widthPx }}
      onMouseEnter={onEnter}
      title={`${dayLabel(day)} · ${point.detail}`}
    >
      <span
        className={cn(
          "absolute inset-0 transition-opacity",
          tone === "ok" ? "bg-ok" : "bg-accent",
          active ? "opacity-100" : "opacity-80 group-hover:opacity-100",
        )}
      />
      {failedHeight > 0 ? (
        <span
          className="bg-hold absolute inset-x-0 bottom-0"
          style={{ height: failedHeight }}
          aria-hidden="true"
        />
      ) : null}
    </span>
  );
}

/**
 * Every day in the window, with its point where one exists.
 *
 * The API returns only days that recorded something, so the gaps have to be put back
 * here to keep the axis honest: without this, four deploys spread over a month would
 * render as four adjacent columns and read as four consecutive days.
 */
function spanDays(points: Plot[], windowDays: number): { day: string; point: Plot | null }[] {
  // The caller renders an empty state instead of a plot, but it is a hook that runs
  // this first and hooks cannot be skipped — so an empty series has to be answered
  // here rather than guarded against outside.
  if (points.length === 0) return [];

  const byDay = new Map(points.map((point) => [point.day, point]));
  const last = points[points.length - 1];
  const end = new Date(`${last.day}T00:00:00Z`);
  const first = new Date(`${points[0].day}T00:00:00Z`);

  // The window is what the reader asked for, but a series reaching further back than
  // the window (or a window far wider than the data) would both distort the axis, so
  // it spans whichever is smaller.
  const span = Math.min(windowDays, Math.round((+end - +first) / 86_400_000) + 1);

  return Array.from({ length: span }, (_, index) => {
    const date = new Date(end);
    date.setUTCDate(date.getUTCDate() - (span - 1 - index));
    const day = date.toISOString().slice(0, 10);
    return { day, point: byDay.get(day) ?? null };
  });
}

function dayLabel(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}
