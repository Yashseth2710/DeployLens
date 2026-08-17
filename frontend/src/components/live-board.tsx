"use client";

import { ButtonLink } from "@/components/button";
import { LiveActivity } from "@/components/live-activity";
import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { SyncLine } from "@/components/sync-line";
import { useActivityBoard, useSession } from "@/lib/queries";

/**
 * The Live page. Nothing here is asked for by hand: the board polls itself, and
 * asking for it is what pulls from GitHub, so an open tab stays current.
 */
export function LiveBoard() {
  const session = useSession();
  const signedIn = Boolean(session.data);
  const board = useActivityBoard(signedIn);

  if (!session.isPending && !signedIn) {
    return (
      <Sheet>
        <SheetHead title="Live" />
        <Notice
          title="Sign in to watch your pipeline"
          detail="Live activity is read from the repositories connected to your GitHub account."
          action={
            <ButtonLink href="/api/auth/github" variant="primary">
              Sign in with GitHub
            </ButtonLink>
          }
        />
      </Sheet>
    );
  }

  if (board.error) {
    return (
      <Sheet>
        <SheetHead title="Live" />
        <Notice tone="problem" title="Could not read activity" detail={board.error.message} />
      </Sheet>
    );
  }

  const data = board.data;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="flex flex-col gap-2">
          <h1 className="text-rank-b">Live activity</h1>
          <p className="text-ink-quiet">
            Everything currently running across your projects, and what has just landed. This page
            watches on its own.
          </p>
        </div>
        <SyncLine lastSyncedAt={data?.last_synced_at ?? null} failed={data?.failed ?? 0} />
      </div>

      <LiveActivity items={data?.items ?? []} loading={board.isPending} title="On press" />
    </div>
  );
}
