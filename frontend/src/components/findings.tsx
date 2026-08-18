"use client";

import Link from "next/link";

import { ExpandingList } from "@/components/expanding-list";
import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { cn } from "@/lib/cn";
import { formatWhen } from "@/lib/outcome";
import type { Finding, FindingKind, RepositoryFindings } from "@/lib/types";

/**
 * The plate label each kind of finding is filed under. A developer scanning the
 * sheet reads these before the sentences, so they name the fault rather than the
 * measurement: "FLAKY" is a verdict, "same commit varied" is evidence for it.
 *
 * The tone carries severity — broken now in hold, unreliable in wait — but never
 * alone: the label says which it is in words, so the sheet reads without hue.
 */
const COLLAPSED_LENGTH = 5;

const KIND: Record<FindingKind, { label: string; tone: string }> = {
  streak: { label: "Failing now", tone: "text-hold" },
  chronic: { label: "Unreliable", tone: "text-hold" },
  flaky: { label: "Flaky", tone: "text-wait" },
  branch: { label: "Branch", tone: "text-wait" },
  slowdown: { label: "Slower", tone: "text-ink" },
};

/**
 * What is going wrong in one project, and why it counts as wrong.
 *
 * Every row is a comparison the developer would otherwise have to make by eye
 * across a page of runs: two verdicts on one commit, a rate against a sample, a
 * streak that is still going. The sheet is absent rather than reassuring when
 * there is nothing to say — a standing "all clear" panel trains people to skip
 * the place the real warnings will appear.
 */
export function Findings({
  findings,
  loading,
  windowDays,
}: {
  findings: Finding[];
  loading: boolean;
  windowDays: number;
}) {
  if (loading) {
    return (
      <Sheet>
        <SheetHead title="What is going wrong" />
        <div className="px-5 py-8" aria-busy="true">
          <span className="bg-rule block h-3 w-48 animate-pulse rounded-[1px]" />
        </div>
      </Sheet>
    );
  }

  return (
    <Sheet>
      <SheetHead
        title="What is going wrong"
        meta={findings.length > 0 ? `${findings.length} · ${windowDays} d` : `${windowDays} d`}
      />
      {findings.length === 0 ? (
        <Notice
          size="compact"
          title="Nothing is failing in a pattern"
          detail="Repeat failures, one commit deciding both ways, and builds slowing against their own pace — none in this window."
        />
      ) : (
        <ExpandingList items={findings} collapsedLength={COLLAPSED_LENGTH} noun="findings">
          {(finding, index) => (
            <FindingRow key={`${finding.kind}-${finding.subject}-${index}`} finding={finding} />
          )}
        </ExpandingList>
      )}
    </Sheet>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  const kind = KIND[finding.kind];

  return (
    <li className="border-rule grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-1 border-b px-5 py-3.5 last:border-b-0 sm:grid-cols-[7rem_minmax(0,1fr)_auto]">
      <span className={cn("label !tracking-[0.14em]", kind.tone)}>{kind.label}</span>
      {/* Its own row on a narrow screen: sharing one with the label would leave the
          sentence a few words wide and break it over four lines. */}
      <span className="col-span-2 flex min-w-0 flex-wrap items-baseline gap-x-2.5 gap-y-1 sm:col-span-1">
        <span className="text-ink truncate font-mono text-[0.8125rem]">{finding.subject}</span>
        <span className="text-ink-quiet text-[0.8125rem]">{finding.detail}</span>
      </span>
      <span className="label col-start-2 row-start-1 text-right !tracking-[0.08em] sm:col-start-auto sm:row-start-auto">
        {formatWhen(finding.last_seen_at)}
        {finding.run_url ? (
          <>
            {" · "}
            <a
              href={finding.run_url}
              target="_blank"
              rel="noreferrer"
              className="!text-accent decoration-accent/40 hover:decoration-accent underline underline-offset-[3px] transition-colors"
            >
              the run ↗
            </a>
          </>
        ) : null}
      </span>
    </li>
  );
}

/**
 * The dashboard's version: which project to open, not what is wrong with it.
 *
 * Deliberately short. The dashboard's job is to point, and a band that tried to
 * explain every finding would be the project page printed six times over.
 */
export function AttentionBand({ repositories }: { repositories: RepositoryFindings[] }) {
  if (repositories.length === 0) return null;

  const total = repositories.reduce((count, row) => count + row.findings.length, 0);

  return (
    <Sheet>
      <SheetHead
        title="Needs attention"
        meta={`${total} across ${repositories.length} project${repositories.length === 1 ? "" : "s"}`}
      />
      <ul>
        {repositories.map((row) => (
          <li
            key={row.repository_id}
            className="border-rule flex flex-col gap-2 border-b px-5 py-3.5 last:border-b-0"
          >
            <Link
              href={`/repositories/${row.repository_id}`}
              className="text-ink hover:!text-accent w-fit truncate transition-colors"
            >
              {row.full_name}
            </Link>
            <ul className="flex flex-col gap-1">
              {row.findings.map((finding, index) => (
                <li
                  key={`${finding.kind}-${index}`}
                  className="grid items-baseline gap-x-4 gap-y-0.5 sm:grid-cols-[7rem_minmax(0,1fr)]"
                >
                  <span className={cn("label !tracking-[0.14em]", KIND[finding.kind].tone)}>
                    {KIND[finding.kind].label}
                  </span>
                  <span className="text-ink-quiet min-w-0 text-[0.8125rem]">
                    <span className="text-ink font-mono">{finding.subject}</span> · {finding.detail}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}
