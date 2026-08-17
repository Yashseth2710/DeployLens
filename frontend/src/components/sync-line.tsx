"use client";

import { cn } from "@/lib/cn";
import { formatWhen } from "@/lib/outcome";

/**
 * A receipt, not a control. The page collects on its own and there is nothing to
 * press — this only says so, and says when GitHub was last read, so an unchanged
 * number can be told apart from a page that has stopped looking.
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
  const broken = failed > 0;

  return (
    <span
      className={cn(
        "label inline-flex items-center gap-2 !tracking-[0.08em]",
        broken && "!text-hold",
        className,
      )}
    >
      {broken ? null : <WatchMark />}
      {broken
        ? `${failed} repositor${failed === 1 ? "y" : "ies"} could not be read`
        : lastSyncedAt
          ? `Watching · read ${formatWhen(lastSyncedAt)}`
          : "Watching · first read on the way"}
    </span>
  );
}

/**
 * The only thing on a quiet page that moves. Without it the line reads as a
 * timestamp that might be stuck rather than as a page still doing its job.
 */
function WatchMark() {
  return (
    <span
      className="bg-ok/70 inline-block h-1.5 w-1.5 animate-pulse rounded-full"
      aria-hidden="true"
    />
  );
}
