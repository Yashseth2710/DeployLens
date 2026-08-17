"use client";

import { useState } from "react";

import { Button } from "@/components/button";
import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { ControlBar, OutcomeMark, type Outcome } from "@/components/status";
import { cn } from "@/lib/cn";
import { formatWhen } from "@/lib/outcome";
import {
  useAddHealthCheck,
  useHealthChecks,
  useHealthResults,
  useRemoveHealthCheck,
  useUpdateHealthCheck,
} from "@/lib/queries";
import type { HealthCheck, HealthResult } from "@/lib/types";

// The API refuses a fourth, so the form is withdrawn rather than left to fail.
const MAX_ENDPOINTS = 3;
const PROBE_STRIP_LENGTH = 24;
const FIRST_READ_WINDOW_MS = 60_000;

// Typed input is set in the mono face the readings use, so what is entered and what
// comes back are the same voice.
const FIELD =
  "border-rule bg-ground focus-visible:border-accent text-ink w-full border px-3 py-2 font-mono text-[0.8125rem] outline-none";

const CADENCES = [
  { minutes: 60, label: "hourly" },
  { minutes: 180, label: "every 3 hours" },
  { minutes: 360, label: "every 6 hours" },
  { minutes: 720, label: "twice a day" },
  { minutes: 1440, label: "daily" },
];

/**
 * The one reading DeployLens cannot collect on its own. Runs, deploys and pull
 * requests all come from GitHub, but nothing there knows whether the thing that
 * shipped is answering — so uptime stays unmeasured until somebody names a URL,
 * and a quarter of the health score stays unmeasurable with it.
 */
export function EndpointMonitor({ repositoryId }: { repositoryId: string }) {
  const checks = useHealthChecks(repositoryId);
  const [adding, setAdding] = useState(false);

  const endpoints = checks.data ?? [];
  const room = endpoints.length < MAX_ENDPOINTS;

  return (
    <Sheet>
      <SheetHead
        title="Endpoint monitoring"
        meta={endpoints.length > 0 ? `${endpoints.length} of ${MAX_ENDPOINTS}` : undefined}
        action={
          room && !adding && endpoints.length > 0 ? (
            <Button variant="secondary" size="compact" onClick={() => setAdding(true)}>
              Watch another
            </Button>
          ) : null
        }
      />

      {adding ? <EndpointForm repositoryId={repositoryId} onDone={() => setAdding(false)} /> : null}

      {checks.isPending ? (
        <PullingRows />
      ) : checks.error ? (
        <Notice
          tone="problem"
          title="Could not read what is being watched"
          detail={checks.error.message}
          action={<Button onClick={() => void checks.refetch()}>Try again</Button>}
        />
      ) : endpoints.length === 0 && !adding ? (
        <Notice
          title="Nothing is being watched yet"
          detail="GitHub can say a deploy succeeded; only the deployed address can say it is answering. Name one and DeployLens reads it on a schedule, which is what the uptime reading above is measured from."
          action={
            <Button variant="primary" onClick={() => setAdding(true)}>
              Watch an endpoint
            </Button>
          }
        />
      ) : (
        <ul>
          {endpoints.map((check) => (
            <EndpointRow key={check.id} check={check} />
          ))}
        </ul>
      )}
    </Sheet>
  );
}

function EndpointRow({ check }: { check: HealthCheck }) {
  const results = useHealthResults(check.id, PROBE_STRIP_LENGTH, justAdded(check));
  const update = useUpdateHealthCheck();
  const remove = useRemoveHealthCheck();
  const [confirming, setConfirming] = useState(false);

  const reads = results.data ?? [];
  const latest = reads[0] ?? null;
  const busy = update.isPending || remove.isPending;
  const failure = update.error ?? remove.error;

  return (
    <li className="border-rule flex flex-col gap-3 border-b px-5 py-4 last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="flex items-center gap-2.5">
            <OutcomeMark
              outcome={reading(check, latest)}
              className={tone(reading(check, latest))}
            />
            <a
              href={check.url}
              target="_blank"
              rel="noreferrer"
              className="text-ink hover:decoration-accent truncate underline decoration-transparent underline-offset-[3px] transition-colors"
            >
              {stripScheme(check.url)}
            </a>
          </span>
          <span className="label !tracking-[0.08em]">
            {cadence(check.interval_minutes)} · expects {check.expected_status}
            {check.enabled ? "" : " · paused"}
            {latest ? ` · read ${formatWhen(latest.checked_at)}` : " · not read yet"}
          </span>
          {latest?.error_message ? (
            <span className="label !text-hold !tracking-[0.08em]">{latest.error_message}</span>
          ) : null}
          {failure ? (
            <span className="label !text-hold !tracking-[0.08em]">{failure.message}</span>
          ) : null}
        </div>

        <div className="flex items-center gap-4">
          <div className="flex flex-col items-end gap-1">
            <span className="text-rank-c text-ink font-sans" data-numeric>
              {latest?.response_time_ms != null ? `${latest.response_time_ms} ms` : "—"}
            </span>
            <span className="label !tracking-[0.08em]">{uptimeOf(reads) ?? "no reads yet"}</span>
          </div>

          {confirming ? (
            <div className="flex items-center gap-1.5">
              <Button
                variant="primary"
                size="compact"
                disabled={busy}
                onClick={() => remove.mutate(check.id)}
              >
                {remove.isPending ? "Removing…" : "Remove"}
              </Button>
              <Button variant="quiet" size="compact" onClick={() => setConfirming(false)}>
                Keep
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <Button
                variant="quiet"
                size="compact"
                disabled={busy}
                onClick={() => update.mutate({ id: check.id, enabled: !check.enabled })}
              >
                {check.enabled ? "Pause" : "Resume"}
              </Button>
              <Button variant="quiet" size="compact" onClick={() => setConfirming(true)}>
                Remove
              </Button>
            </div>
          )}
        </div>
      </div>

      {reads.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <ControlBar outcomes={reads.map((read) => outcomeOf(read))} />
          <span className="label !text-ink-faint !tracking-[0.1em]">
            Last {reads.length} read{reads.length === 1 ? "" : "s"} · newest first
          </span>
        </div>
      ) : null}
    </li>
  );
}

/**
 * Three fields, because a URL alone leaves two questions the probe has to answer
 * anyway: what counts as healthy, and how often to ask. Both carry a default that
 * is right for a deployed web app, so the form is one field for most people.
 */
function EndpointForm({ repositoryId, onDone }: { repositoryId: string; onDone: () => void }) {
  const add = useAddHealthCheck(repositoryId);
  const [url, setUrl] = useState("https://");
  const [expected, setExpected] = useState(200);
  const [minutes, setMinutes] = useState(60);

  return (
    <form
      className="border-rule bg-booth flex flex-col gap-4 border-b px-5 py-4"
      onSubmit={(event) => {
        event.preventDefault();
        add.mutate(
          { url: url.trim(), expected_status: expected, interval_minutes: minutes },
          { onSuccess: onDone },
        );
      }}
    >
      <div className="flex flex-wrap items-end gap-x-5 gap-y-4">
        <label className="flex min-w-[18rem] flex-1 flex-col gap-1.5">
          <span className="label">Address to read</span>
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            type="url"
            required
            autoFocus
            placeholder="https://your-app.vercel.app/api/health"
            className={FIELD}
          />
        </label>

        <label className="flex w-24 flex-col gap-1.5">
          <span className="label">Expects</span>
          <input
            value={expected}
            onChange={(event) => setExpected(Number(event.target.value))}
            type="number"
            min={100}
            max={599}
            required
            className={FIELD}
            data-numeric
          />
        </label>

        <label className="flex w-40 flex-col gap-1.5">
          <span className="label">Read it</span>
          <span className="relative flex items-center">
            <select
              value={minutes}
              onChange={(event) => setMinutes(Number(event.target.value))}
              className={cn(FIELD, "appearance-none pr-8")}
            >
              {CADENCES.map((option) => (
                <option key={option.minutes} value={option.minutes}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="text-ink-faint pointer-events-none absolute right-3 text-[0.6rem]">
              ▼
            </span>
          </span>
        </label>
      </div>

      {add.error ? (
        <p className="label !text-hold !tracking-[0.08em]">{add.error.message}</p>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" size="compact" disabled={add.isPending}>
          {add.isPending ? "Reading it now…" : "Start watching"}
        </Button>
        <Button type="button" variant="quiet" size="compact" onClick={onDone}>
          Cancel
        </Button>
        <span className="label !text-ink-faint !tracking-[0.08em]">
          Read once straight away, then on the cadence above · public addresses only
        </span>
      </div>
    </form>
  );
}

/**
 * A paused check keeps its last result, but that result is no longer a claim about
 * now, so it reads as unmeasured rather than as whatever it said when it stopped.
 */
function reading(check: HealthCheck, latest: HealthResult | null): Outcome {
  if (!check.enabled || !latest) return "none";
  return outcomeOf(latest);
}

/**
 * The API reads a new endpoint straight away, so its first result is seconds behind
 * the row appearing. Only that window is worth waiting through; an endpoint added
 * yesterday with nothing recorded has an answer already.
 */
function justAdded(check: HealthCheck): boolean {
  return Date.now() - new Date(check.created_at).getTime() < FIRST_READ_WINDOW_MS;
}

function outcomeOf(result: HealthResult): Outcome {
  return result.status === "up" ? "ok" : "hold";
}

function uptimeOf(reads: HealthResult[]): string | null {
  if (reads.length === 0) return null;
  const up = reads.filter((read) => read.status === "up").length;
  return `${Math.round((up / reads.length) * 100)}% up`;
}

function cadence(minutes: number): string {
  return CADENCES.find((option) => option.minutes === minutes)?.label ?? `every ${minutes} min`;
}

function stripScheme(url: string): string {
  return url.replace(/^https?:\/\//, "");
}

function tone(outcome: Outcome): string {
  if (outcome === "ok") return "text-ok";
  if (outcome === "hold") return "text-hold";
  return "text-ink-faint";
}

function PullingRows() {
  return (
    <ul aria-busy="true">
      {[0, 1].map((row) => (
        <li key={row} className="border-rule border-b px-5 py-5 last:border-b-0">
          <span
            className="bg-rule block h-3 animate-pulse rounded-[1px]"
            style={{ width: `${12 + row * 4}rem`, animationDelay: `${row * 120}ms` }}
          />
        </li>
      ))}
    </ul>
  );
}
