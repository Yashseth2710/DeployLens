"use client";

import { cn } from "@/lib/cn";

export const WINDOWS = [7, 30, 90, 365] as const;
export type WindowDays = (typeof WINDOWS)[number];

/**
 * One control retunes the whole sheet. Thirty days is the default because probe
 * history is kept for a month, so a wider uptime reading comes from a shrinking
 * sample. A year is offered because a project that has finished shipping has
 * nothing in the last month and its history is exactly what is worth reading.
 */
export function WindowControl({
  value,
  onChange,
}: {
  value: WindowDays;
  onChange: (days: WindowDays) => void;
}) {
  return (
    <div className="border-rule flex items-center border" role="group" aria-label="Reading window">
      {WINDOWS.map((days) => (
        <button
          key={days}
          type="button"
          onClick={() => onChange(days)}
          aria-pressed={days === value}
          className={cn(
            "label border-rule px-3 py-1.5 !tracking-[0.12em] transition-colors not-last:border-r",
            days === value ? "bg-accent !text-accent-ink" : "hover:bg-sheet-raised hover:!text-ink",
          )}
        >
          {days === 365 ? "1 y" : `${days} d`}
        </button>
      ))}
    </div>
  );
}
