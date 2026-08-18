import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Nothing here yet, or something went wrong. Both are ordinary states on a
 * fresh account, so neither gets an alarm: a plain line of type on the sheet,
 * with the one action that resolves it.
 *
 * `size` is how much of the page the absence is worth. A fresh account meeting
 * an empty dashboard is being onboarded and the notice is the content, so it
 * stands full height. A working project reporting that nothing is failing is
 * saying one thing in passing, and a sheet that reserves eighty points of air
 * to say it reads as a hole in the page rather than as good news.
 */
export function Notice({
  title,
  detail,
  action,
  tone = "quiet",
  size = "full",
  className,
}: {
  title: string;
  detail?: ReactNode;
  action?: ReactNode;
  tone?: "quiet" | "problem";
  size?: "full" | "compact";
  className?: string;
}) {
  const compact = size === "compact";

  return (
    <div
      className={cn(
        "flex flex-col items-start px-5",
        compact ? "gap-1.5 py-4" : "gap-3 py-10",
        className,
      )}
    >
      <p
        className={cn(
          compact ? "text-rank-d" : "text-rank-c",
          tone === "problem" ? "text-hold" : "text-ink",
        )}
      >
        {title}
      </p>
      {detail ? <p className="text-ink-quiet max-w-[68ch]">{detail}</p> : null}
      {action}
    </div>
  );
}
