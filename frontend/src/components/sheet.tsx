import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * A panel bounded by crop marks instead of a border. The corners register the
 * sheet against the page; nothing is boxed in.
 */
export function Sheet({
  children,
  className,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "article" | "div" | "aside";
}) {
  return (
    <Tag className={cn("sheet rounded-sheet", className)}>
      {children}
      <span className="crop-foot" aria-hidden="true" />
    </Tag>
  );
}

/**
 * The job ticket at the head of a sheet: what this plate is, and the one fact
 * worth reading before the plate itself.
 */
export function SheetHead({
  title,
  meta,
  action,
}: {
  title: string;
  meta?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="border-rule flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 border-b px-5 py-3.5">
      <div className="flex items-baseline gap-3">
        <h2 className="label !text-ink-quiet">{title}</h2>
        {meta ? <span className="label">{meta}</span> : null}
      </div>
      {action}
    </header>
  );
}
