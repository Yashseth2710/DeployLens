"use client";

import { ExpandingList } from "@/components/expanding-list";
import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { formatDuration, formatWhen } from "@/lib/outcome";
import type { RunGroup } from "@/lib/types";

const COLLAPSED_LENGTH = 5;

/**
 * Which workflow, or which branch, is costing the most.
 *
 * A project has two of these side by side and they are never the same length —
 * two workflows run against twenty-four branches is the ordinary shape, not the
 * edge case. Ranking every row identically hands the same weight to a branch
 * that ran once and one that ran nineteen times and failed eight, so each row
 * carries its share of the total as a rule beneath it. The eye then finds the
 * expensive rows without reading a single number.
 */
export function GroupSheet({
  title,
  groups,
  empty,
  noun,
  collapsedLength = COLLAPSED_LENGTH,
}: {
  title: string;
  groups: RunGroup[];
  empty: string;
  noun: string;
  /** Set by a pair of sheets so both open at the same height. */
  collapsedLength?: number;
}) {
  // Share is measured against the busiest row rather than the total: with
  // twenty-four branches every share of the total rounds to a hairline, and the
  // question the sheet answers is which rows are big relative to each other.
  const busiest = Math.max(1, ...groups.map((group) => group.runs));

  return (
    <Sheet className="flex flex-col">
      <SheetHead title={title} meta={groups.length > 0 ? `${groups.length}` : undefined} />
      {groups.length === 0 ? (
        <Notice size="compact" title={empty} />
      ) : (
        <ExpandingList items={groups} collapsedLength={collapsedLength} noun={noun}>
          {(group) => (
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
              <ShareRule runs={group.runs} failed={group.failed} busiest={busiest} />
            </li>
          )}
        </ExpandingList>
      )}
    </Sheet>
  );
}

/**
 * The row's volume drawn against the busiest row, with the failed part filled in
 * hold. It runs the full width under the row on its own track, so the list reads
 * as a ranked chart without becoming one — the numbers stay the record, this is
 * the shape of them. Two points tall rather than one: a hairline that stops
 * partway across reads as a stray underline rather than as a measured bar.
 */
function ShareRule({ runs, failed, busiest }: { runs: number; failed: number; busiest: number }) {
  const share = Math.max(3, Math.round((runs / busiest) * 100));
  const failedShare = failed > 0 ? Math.max(8, (failed / runs) * 100) : 0;

  return (
    <span className="bg-rule/50 col-span-2 mt-1.5 block h-0.5 w-full" aria-hidden="true">
      <span className="bg-accent/70 relative block h-full" style={{ width: `${share}%` }}>
        {failedShare > 0 ? (
          <span
            className="bg-hold absolute inset-y-0 right-0"
            style={{ width: `${failedShare}%` }}
          />
        ) : null}
      </span>
    </span>
  );
}
