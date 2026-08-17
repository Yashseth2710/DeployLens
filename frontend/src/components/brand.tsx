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

export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "text-ink inline-flex items-baseline font-semibold tracking-[-0.035em] select-none",
        className,
      )}
    >
      <span aria-hidden="true" className="inline-flex items-center">
        Depl
        <Aperture className="text-ink mx-[0.03em] translate-y-[0.02em]" />y
        <span className="text-accent">Lens</span>
      </span>
      <span className="sr-only">DeployLens</span>
    </span>
  );
}
