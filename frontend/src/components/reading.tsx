import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * A measured value. The sample it was taken from is part of the reading, not a
 * footnote: a success rate over four runs and one over four hundred are
 * different claims and must not look identical.
 *
 * `value` of null means nothing has been measured, which is a third state
 * distinct from zero and must render as such.
 */
export function Reading({
  label,
  value,
  unit,
  sample,
  absent = "not measured",
  className,
}: {
  label: string;
  value: ReactNode | null;
  unit?: string;
  sample?: string;
  absent?: string;
  className?: string;
}) {
  const measured = value !== null && value !== undefined;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <span className="label">{label}</span>
      {measured ? (
        <span className="text-rank-b text-ink flex items-baseline gap-1 font-sans" data-numeric>
          {value}
          {unit ? <span className="text-rank-c text-ink-quiet">{unit}</span> : null}
        </span>
      ) : (
        <span className="text-rank-c text-ink-faint font-sans italic">{absent}</span>
      )}
      {sample ? <span className="label !text-ink-faint !tracking-[0.1em]">{sample}</span> : null}
    </div>
  );
}
