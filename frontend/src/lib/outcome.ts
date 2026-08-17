import type { Outcome } from "@/components/status";

const DECIDED_FAILURE = ["failure", "timed_out", "startup_failure"];
const IN_FLIGHT = ["queued", "in_progress", "requested", "waiting", "pending"];

/**
 * GitHub keeps adding conclusions, so anything unrecognised lands on "none"
 * rather than being counted as a failure it might not be.
 */
export function outcomeOf(status: string): Outcome {
  if (status === "success") return "ok";
  if (DECIDED_FAILURE.includes(status)) return "hold";
  if (IN_FLIGHT.includes(status)) return "wait";
  return "none";
}

export function formatDuration(seconds: number | null): string | null {
  if (seconds === null) return null;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes > 0 ? `${minutes}:${String(rest).padStart(2, "0")}` : `${rest}s`;
}

export function formatWhen(iso: string | null): string {
  if (!iso) return "never";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days}d ago`;
}

/**
 * A run that has not finished has no conclusion yet, so status carries it.
 */
export function runOutcome(status: string, conclusion: string | null): Outcome {
  return outcomeOf(conclusion ?? status);
}

/**
 * Hours are how the API measures a merge, but nobody says "51 hours" out loud.
 */
export function formatHours(hours: number | null): string | null {
  if (hours === null) return null;
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 48) return `${hours < 10 ? hours.toFixed(1) : Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

export function formatMonth(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export const EVENT_LABEL: Record<string, string> = {
  push: "push",
  pull_request: "pull request",
  schedule: "scheduled",
  workflow_dispatch: "manual",
  release: "release",
  deployment: "deployment",
};
