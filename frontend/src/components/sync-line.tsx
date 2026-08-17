"use client";

import { Button } from "@/components/button";
import { cn } from "@/lib/cn";
import { formatWhen } from "@/lib/outcome";
import { useSyncNow } from "@/lib/queries";

/**
 * The page keeps itself current, so this is a receipt rather than a control: it
 * says when GitHub was last read, and offers the manual pull for the times when
 * someone needs to be sure now rather than in a moment.
 */
export function SyncLine({
  lastSyncedAt,
  failed = 0,
  className,
}: {
  lastSyncedAt: string | null;
  failed?: number;
  className?: string;
}) {
  const sync = useSyncNow();
  const broken = failed > 0;

  return (
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1", className)}>
      <span
        className={cn(
          "label inline-flex items-center gap-2 !tracking-[0.08em]",
          broken && "!text-hold",
        )}
      >
        {broken ? null : <WatchMark />}
        {broken
          ? `${failed} repositor${failed === 1 ? "y" : "ies"} could not be read`
          : lastSyncedAt
            ? `Auto-syncing · read ${formatWhen(lastSyncedAt)}`
            : "Auto-syncing · first read on the way"}
      </span>
      <Button
        variant="quiet"
        size="compact"
        disabled={sync.isPending}
        onClick={() => sync.mutate()}
      >
        {sync.isPending ? "Reading…" : "Read now"}
      </Button>
    </div>
  );
}

/**
 * A steady pulse on the sync line. The page collects on its own, and this is the
 * only thing that says so — without it the button beside it reads as the way the
 * data arrives rather than as the override it is.
 */
function WatchMark() {
  return (
    <span
      className="bg-ok/70 inline-block h-1.5 w-1.5 animate-pulse rounded-full"
      aria-hidden="true"
    />
  );
}
