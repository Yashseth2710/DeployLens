"use client";

import { useState } from "react";

import { ExpandingList } from "@/components/expanding-list";
import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { OutcomeMark, type Outcome } from "@/components/status";
import { cn } from "@/lib/cn";
import { formatWhen } from "@/lib/outcome";
import type { PullRequestRow } from "@/lib/types";

type Filter = "all" | "open" | "merged" | "abandoned";

const FILTERS = ["all", "open", "merged", "abandoned"] as const;

const COLLAPSED_LENGTH = 5;

/**
 * Pull requests read by what became of them. GitHub calls a merged one and an
 * abandoned one both "closed", and that difference — work that shipped against
 * work that was dropped — is the only reason this list is worth keeping.
 */
export function PullRequestList({
  pullRequests,
  loading,
  title = "Pull requests",
  showRepository = false,
}: {
  pullRequests: PullRequestRow[];
  loading: boolean;
  title?: string;
  showRepository?: boolean;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const shown = pullRequests.filter((row) => filter === "all" || row.outcome === filter);

  return (
    <Sheet>
      <SheetHead
        title={title}
        meta={`${shown.length} of ${pullRequests.length}`}
        action={
          <div
            className="border-rule flex items-center border"
            role="group"
            aria-label="Filter pull requests"
          >
            {FILTERS.map((option) => (
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
          <span className="bg-rule block h-3 w-52 animate-pulse rounded-[1px]" />
        </div>
      ) : shown.length === 0 ? (
        <Notice
          title={filter === "all" ? "No pull requests collected" : `Nothing ${filter}`}
          detail={
            filter === "all"
              ? "Pull requests are collected on a slower cadence than runs, because a merged one stays merged. The first collection reaches back through the project's whole history."
              : "Change the filter to see the rest."
          }
        />
      ) : (
        <ExpandingList
          key={filter}
          items={shown}
          collapsedLength={COLLAPSED_LENGTH}
          noun="pull requests"
        >
          {(row) => (
            <li
              key={row.id}
              className="border-rule hover:bg-sheet-raised grid grid-cols-[auto_minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-1 border-b px-5 py-3 transition-colors last:border-b-0"
            >
              <span className="flex items-center gap-2">
                <OutcomeMark outcome={markOf(row.outcome)} className={toneOf(row.outcome)} />
                <span className="label !tracking-[0.08em]" data-numeric>
                  #{row.number}
                </span>
              </span>

              <a
                href={row.html_url ?? undefined}
                target="_blank"
                rel="noreferrer"
                className="text-ink hover:text-accent truncate transition-colors"
              >
                {row.title}
                {row.draft ? <span className="label ml-2 !tracking-[0.1em]">draft</span> : null}
              </a>

              <span className={cn("label !tracking-[0.12em]", toneOf(row.outcome))}>
                {row.outcome}
              </span>

              <span className="label col-span-3 truncate !tracking-[0.08em]">
                {showRepository ? `${row.repository_full_name} · ` : ""}
                {row.author ?? "unknown"}
                {row.head_branch ? ` · ${row.head_branch} → ${row.base_branch ?? "?"}` : ""}
                {" · "}
                {when(row)}
              </span>
            </li>
          )}
        </ExpandingList>
      )}
    </Sheet>
  );
}

function when(row: PullRequestRow): string {
  if (row.outcome === "merged") return `merged ${formatWhen(row.merged_at)}`;
  if (row.outcome === "abandoned") return `closed ${formatWhen(row.closed_at)}`;
  return `opened ${formatWhen(row.opened_at)}`;
}

function markOf(outcome: PullRequestRow["outcome"]): Outcome {
  if (outcome === "merged") return "ok";
  if (outcome === "abandoned") return "hold";
  return "wait";
}

function toneOf(outcome: PullRequestRow["outcome"]): string {
  if (outcome === "merged") return "text-ok";
  if (outcome === "abandoned") return "text-hold";
  return "text-wait";
}
