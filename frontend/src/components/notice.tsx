import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Nothing here yet, or something went wrong. Both are ordinary states on a
 * fresh account, so neither gets an alarm: a plain line of type on the sheet,
 * with the one action that resolves it.
 */
export function Notice({
  title,
  detail,
  action,
  tone = "quiet",
  className,
}: {
  title: string;
  detail?: ReactNode;
  action?: ReactNode;
  tone?: "quiet" | "problem";
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-start gap-3 px-5 py-10", className)}>
      <p className={cn("text-rank-c", tone === "problem" ? "text-hold" : "text-ink")}>{title}</p>
      {detail ? <p className="text-ink-quiet max-w-[60ch]">{detail}</p> : null}
      {action}
    </div>
  );
}
