"use client";

import { useEffect, useState } from "react";

import { ExpandingList } from "@/components/expanding-list";
import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { OutcomeMark, type Outcome } from "@/components/status";
import { cn } from "@/lib/cn";
import { formatWhen, outcomeOf } from "@/lib/outcome";
import type { ActivityItem } from "@/lib/types";

const COLLAPSED_LENGTH = 5;

/**
 * What is happening right now. A run that is still going is the one thing on this
 * product that cannot be read from history, and it is the reason to leave the page
 * open — so it leads, it counts up in real time, and when it lands it settles in
 * place rather than disappearing and being replaced by a different-looking row.
 */
export function LiveActivity({
  items,
  loading,
  title = "Live now",
  compact = false,
}: {
  items: ActivityItem[];
  loading: boolean;
  title?: string;
  compact?: boolean;
}) {
  const live = items.filter((item) => item.live);
  const settled = items.filter((item) => !item.live);
  // Running first where space is tight, so the rows that cannot be read from
  // history are the ones standing open.
  const shown = compact ? [...live, ...settled] : items;
  const now = useTick(live.length > 0);

  return (
    <Sheet>
      <SheetHead
        title={title}
        meta={
          live.length > 0 ? (
            <span className="text-wait inline-flex items-center gap-2">
              <PressMark />
              {live.length} running
            </span>
          ) : (
            "all quiet"
          )
        }
      />

      {loading && items.length === 0 ? (
        <div className="px-5 py-8" aria-busy="true">
          <span className="bg-rule block h-3 w-44 animate-pulse rounded-[1px]" />
        </div>
      ) : shown.length === 0 ? (
        <Notice
          title="Nothing running"
          detail="No workflow or deployment is in flight. This page watches on its own — when something starts, it appears here without a refresh."
        />
      ) : (
        <ExpandingList items={shown} collapsedLength={COLLAPSED_LENGTH} noun="items" live>
          {(item) => <Row key={`${item.kind}-${item.id}`} item={item} now={now} />}
        </ExpandingList>
      )}
    </Sheet>
  );
}

function Row({ item, now }: { item: ActivityItem; now: number }) {
  const outcome = stateOf(item);
  const elapsed = item.live ? sinceStart(item.started_at, now) : null;

  return (
    <li
      className={cn(
        "border-rule grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 border-b px-5 py-3.5 transition-colors duration-500 last:border-b-0",
        item.live && "bg-wait-quiet/40",
      )}
    >
      <OutcomeMark
        outcome={outcome}
        className={cn(toneOf(outcome), item.live && "animate-pulse")}
      />

      <div className="flex min-w-0 flex-col gap-1">
        <a
          href={item.url ?? undefined}
          target="_blank"
          rel="noreferrer"
          className={cn(
            "truncate transition-colors",
            item.url ? "text-ink hover:text-accent" : "text-ink",
          )}
        >
          {item.title}
        </a>
        <span className="label truncate !tracking-[0.08em]">
          {item.repository_full_name}
          {item.detail ? ` · ${item.detail}` : ""}
        </span>
      </div>

      <div className="flex flex-col items-end gap-1">
        <span
          className={cn(
            "label !tracking-[0.12em] transition-colors duration-500",
            item.live ? "!text-wait" : toneOf(outcome),
          )}
        >
          {stateWord(item)}
        </span>
        <span className="label !text-ink-faint !tracking-[0.08em]" data-numeric>
          {elapsed ?? finishedAt(item)}
        </span>
      </div>
    </li>
  );
}

/**
 * The registration mark on a plate being pulled. It is the only thing on the page
 * that moves while nothing else changes, which is what says the page is watching.
 */
function PressMark() {
  return (
    <span className="relative flex h-2 w-2" aria-hidden="true">
      <span className="bg-wait absolute inline-flex h-full w-full animate-ping rounded-full opacity-60" />
      <span className="bg-wait relative inline-flex h-2 w-2 rounded-full" />
    </span>
  );
}

/**
 * One timer for the whole board rather than one per row, and none at all when
 * nothing is running — an idle page should not re-render every second.
 */
function useTick(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);

  return now;
}

function stateOf(item: ActivityItem): Outcome {
  if (item.live) return "wait";
  return outcomeOf(item.conclusion ?? item.status);
}

function stateWord(item: ActivityItem): string {
  if (item.live) return item.kind === "deploy" ? "Deploying" : "Running";
  const outcome = outcomeOf(item.conclusion ?? item.status);
  if (outcome === "ok") return item.kind === "deploy" ? "Deployed" : "Passed";
  if (outcome === "hold") return "Failed";
  return item.conclusion ?? item.status;
}

function sinceStart(startedAt: string | null, now: number): string | null {
  if (!startedAt) return null;
  const seconds = Math.max(0, Math.round((now - new Date(startedAt).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${String(seconds % 60).padStart(2, "0")}s`;
}

function finishedAt(item: ActivityItem): string {
  return formatWhen(item.completed_at ?? item.started_at);
}

function toneOf(outcome: Outcome): string {
  if (outcome === "ok") return "text-ok";
  if (outcome === "hold") return "text-hold";
  if (outcome === "wait") return "text-wait";
  return "text-ink-faint";
}
