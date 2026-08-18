"use client";

import { useState, type ReactNode } from "react";

/**
 * A list that opens at a readable height and expands on request.
 *
 * A project with sixty runs is not better read by scrolling past all sixty to
 * reach the next sheet. The first handful answers "what happened lately", which
 * is the question the page is usually open for, and the rest stays one press
 * away rather than gone.
 *
 * A list whose contents change for a reason the reader chose — switching a filter —
 * should open at its collapsed height again, so give it a `key` naming that choice.
 * Without one an expanded sheet stays expanded through the switch, which quietly
 * undoes a collapse the reader asked for.
 */
export function ExpandingList<T>({
  items,
  collapsedLength,
  noun,
  live = false,
  className,
  onToggle,
  children,
}: {
  items: T[];
  collapsedLength: number;
  /** Plural, for the control: "12 more runs". */
  noun: string;
  /** Announces rows as they change, for a list that updates without a reload. */
  live?: boolean;
  /** For a list that has to fill a height its neighbour set. */
  className?: string;
  /** Told when the list opens or closes, for a layout that answers to it. */
  onToggle?: (expanded: boolean) => void;
  /** Renders the whole row, `<li>` included, so each list keeps its own layout. */
  children: (item: T, index: number) => ReactNode;
}) {
  const [open, setOpen] = useState(false);

  const hidden = items.length - collapsedLength;
  // Derived rather than stored, so filtering to a list that fits and back again
  // cannot leave the control reading "show fewer" over rows that are all visible.
  const expanded = open && hidden > 0;
  const shown = expanded ? items : items.slice(0, collapsedLength);

  return (
    <>
      <ul className={className} aria-live={live ? "polite" : undefined}>
        {shown.map(children)}
      </ul>
      {hidden > 0 ? (
        <button
          type="button"
          onClick={() => {
            setOpen(!expanded);
            onToggle?.(!expanded);
          }}
          aria-expanded={expanded}
          className="label border-rule text-ink-quiet hover:bg-sheet-raised hover:!text-ink flex w-full items-center justify-center gap-2 border-t px-5 py-3 !tracking-[0.12em] transition-colors"
        >
          {expanded ? "Show fewer" : `${hidden} more ${noun}`}
          <Chevron open={expanded} />
        </button>
      ) : null}
    </>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 10 10"
      aria-hidden="true"
      className={`h-2.5 w-2.5 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
    >
      <path
        d="M1.5 3.5 5 7 8.5 3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="square"
      />
    </svg>
  );
}
