"use client";

import { useState } from "react";

import { ButtonLink } from "@/components/button";
import { Notice } from "@/components/notice";
import { PullRequestList } from "@/components/pull-request-list";
import { Reading } from "@/components/reading";
import { Sheet, SheetHead } from "@/components/sheet";
import { SyncLine } from "@/components/sync-line";
import { WindowControl, type WindowDays } from "@/components/window-control";
import { formatHours, formatMonth } from "@/lib/outcome";
import {
  isAccessExpired,
  useActivityBoard,
  useOverview,
  usePullRequests,
  useSession,
} from "@/lib/queries";

const LIST_LENGTH = 100;

/**
 * The review side of delivery. Runs say whether the pipeline works; pull requests
 * say whether the work got through it, and commits say whether anybody is writing
 * any. Neither is visible anywhere else in the product.
 */
export function ReviewBoard() {
  const session = useSession();
  const signedIn = Boolean(session.data);
  const [days, setDays] = useState<WindowDays>(30);

  const board = useActivityBoard(signedIn);
  const overview = useOverview(days, signedIn);
  const pullRequests = usePullRequests(LIST_LENGTH, signedIn);

  if (!session.isPending && !signedIn) {
    return (
      <Sheet>
        <SheetHead title="Pull requests" />
        <Notice
          title="Sign in to see your pull requests"
          detail="Pull requests are collected from the repositories connected to your GitHub account."
          action={
            <ButtonLink href="/api/auth/github" variant="primary">
              Sign in with GitHub
            </ButtonLink>
          }
        />
      </Sheet>
    );
  }

  const review = overview.data?.review;
  const window = `${days} d`;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="flex flex-col gap-2">
          <h1 className="text-rank-b">Work through review</h1>
          <p className="text-ink-quiet">
            What was opened, what merged, and what was dropped — across every connected project.
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

      <Sheet>
        <SheetHead
          title="Review and commits"
          meta={
            review?.first_commit_week
              ? `${window} · history from ${formatMonth(review.first_commit_week)}`
              : window
          }
        />
        <div className="grid gap-x-8 gap-y-7 px-5 py-6 sm:grid-cols-2 lg:grid-cols-5">
          <Reading
            label="Merged"
            value={review?.merged || null}
            sample={review?.opened ? `${review.opened} opened in window` : "none opened"}
            absent="none merged"
          />
          <Reading
            label="Merge rate"
            value={review?.merge_rate ?? null}
            unit="%"
            sample={
              review
                ? `${review.merged} of ${review.merged + review.closed_unmerged} decided`
                : undefined
            }
            absent="nothing decided"
          />
          <Reading
            label="Time to merge"
            value={formatHours(review?.median_hours_to_merge ?? null)}
            sample="median"
            absent="nothing merged"
          />
          <Reading
            label="Open now"
            value={review?.open_now || null}
            sample="awaiting review"
            absent="none open"
          />
          <Reading
            label="Commits"
            value={review?.commits || null}
            sample={review ? `${review.commits_per_week}/wk · ${window}` : undefined}
            absent="none in window"
          />
        </div>
      </Sheet>

      <PullRequestList
        pullRequests={pullRequests.data ?? []}
        loading={pullRequests.isPending}
        title="Every pull request"
        showRepository
      />
    </div>
  );
}
