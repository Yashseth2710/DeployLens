import { cn } from "@/lib/cn";

/**
 * The aperture that replaces the o in Deploy: an open ring with the gap at the
 * upper right and the blade pivot at its centre. It is the only mark the brand
 * has, so it doubles as the favicon and as the in-progress indicator.
 */
export function Aperture({
  className,
  spinning = false,
}: {
  className?: string;
  spinning?: boolean;
}) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
      className={cn("h-[0.72em] w-[0.72em] shrink-0", className)}
    >
      <circle
        cx="10"
        cy="10"
        r="7.5"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="butt"
        strokeDasharray="35.5 11.6"
        transform="rotate(-64 10 10)"
        className={cn(spinning && "origin-center motion-safe:animate-[spin_2.4s_linear_infinite]")}
      />
      <circle cx="10" cy="10" r="2.9" className="fill-accent" />
    </svg>
  );
}

/**
 * The wordmark, set solid as one word.
 *
 * "Lens" runs from the accent into the deeper blue it cools toward rather than
 * sitting flat, which is what separates the two halves of the name at a glance
 * without a second hue entering the palette. The gradient is painted through the
 * text itself, so it stays one piece of live type: sharp at any size, correct in
 * both themes, and selectable as "DeployLens".
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "text-ink inline-flex items-baseline font-semibold tracking-[-0.038em] select-none",
        className,
      )}
    >
      <span aria-hidden="true" className="inline-flex items-center">
        Depl
        <Aperture className="text-ink mx-[0.02em] translate-y-[0.02em]" />y
        <span className="from-accent-strong to-accent bg-gradient-to-r bg-clip-text text-transparent">
          Lens
        </span>
      </span>
      <span className="sr-only">DeployLens</span>
    </span>
  );
}
