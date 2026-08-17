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

  return (
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-2", className)}>
      <span className="label !tracking-[0.08em]">
        {failed > 0
          ? `${failed} repositor${failed === 1 ? "y" : "ies"} could not be read`
          : lastSyncedAt
            ? `Synced ${formatWhen(lastSyncedAt)}`
            : "Not synced yet"}
      </span>
      <Button
        variant="quiet"
        size="compact"
        disabled={sync.isPending}
        onClick={() => sync.mutate()}
      >
        {sync.isPending ? "Syncing…" : "Sync now"}
      </Button>
    </div>
  );
}
