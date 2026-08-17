import { cn } from "@/lib/cn";

export type Outcome = "ok" | "hold" | "wait" | "none";

const STAMP = {
  ok: { text: "OK TO PRINT", tone: "border-ok/60 text-ok bg-ok-quiet" },
  hold: { text: "HOLD", tone: "border-hold/60 text-hold bg-hold-quiet" },
  wait: { text: "ON PRESS", tone: "border-wait/60 text-wait bg-wait-quiet" },
  none: { text: "NOT PULLED", tone: "border-rule text-ink-faint bg-transparent" },
} as const;

/**
 * The sign-off a press operator writes on an approved sheet. Colour is the
 * second signal here, never the only one: each state carries its own words and
 * its own drawn mark, so the sheet still reads without hue.
 */
export function SignOff({ outcome, className }: { outcome: Outcome; className?: string }) {
  const stamp = STAMP[outcome];
  return (
    <span
      className={cn(
        "label inline-flex items-center gap-1.5 border px-2 py-1 !text-[0.625rem] !tracking-[0.14em]",
        stamp.tone,
        className,
      )}
    >
      <OutcomeMark outcome={outcome} />
      {stamp.text}
    </span>
  );
}

export function OutcomeMark({ outcome, className }: { outcome: Outcome; className?: string }) {
  return (
    <svg viewBox="0 0 10 10" aria-hidden="true" className={cn("h-2.5 w-2.5 shrink-0", className)}>
      {outcome === "ok" && (
        <path
          d="M1.5 5.4 4 8 8.5 2"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="square"
        />
      )}
      {outcome === "hold" && (
        <path
          d="M1.8 1.8 8.2 8.2M8.2 1.8 1.8 8.2"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="square"
        />
      )}
      {outcome === "wait" && (
        <circle cx="5" cy="5" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
      )}
      {outcome === "none" && (
        <path d="M1.5 5h7" fill="none" stroke="currentColor" strokeWidth="1.6" />
      )}
    </svg>
  );
}

/**
 * The colour control bar printed down the edge of a press sheet. Here each
 * patch is one deploy, oldest at the far end, so the run of recent history
 * reads as a strip rather than a chart.
 */
export function ControlBar({
  outcomes,
  className,
  orientation = "horizontal",
}: {
  outcomes: Outcome[];
  className?: string;
  orientation?: "horizontal" | "vertical";
}) {
  // Height carries the outcome as well as hue: a failed pull is a full-height
  // patch, a good one sits short. The strip still reads in greyscale.
  const patch: Record<Outcome, string> = {
    ok: "bg-ok",
    hold: "bg-hold",
    wait: "bg-wait",
    none: "bg-rule",
  };
  const extent: Record<Outcome, string> = {
    ok: orientation === "vertical" ? "w-2" : "h-2.5",
    hold: orientation === "vertical" ? "w-4" : "h-5",
    wait: orientation === "vertical" ? "w-3" : "h-3.5",
    none: orientation === "vertical" ? "w-1.5" : "h-1.5",
  };

  return (
    <div
      className={cn(
        "flex gap-[3px]",
        orientation === "vertical" ? "flex-col items-start" : "flex-row items-end",
        className,
      )}
    >
      {outcomes.map((outcome, index) => (
        <span
          key={index}
          className={cn(
            "block",
            orientation === "vertical" ? "h-1.5" : "w-1.5",
            extent[outcome],
            patch[outcome],
          )}
        />
      ))}
    </div>
  );
}

/**
 * The density step wedge a printer reads to check ink laydown. Ten steps, so a
 * score is judged by how far the wedge fills rather than by parsing a number.
 */
export function StepWedge({
  value,
  className,
  steps = 10,
}: {
  value: number | null;
  className?: string;
  steps?: number;
}) {
  const filled = value === null ? 0 : Math.round((value / 100) * steps);

  return (
    <div className={cn("flex items-end gap-[3px]", className)} aria-hidden="true">
      {Array.from({ length: steps }, (_, index) => (
        <span
          key={index}
          className={cn(
            "w-2 rounded-[1px] transition-colors duration-300",
            index < filled ? "bg-accent" : "bg-rule",
          )}
          style={{ height: `${6 + index * 1.6}px` }}
        />
      ))}
    </div>
  );
}
