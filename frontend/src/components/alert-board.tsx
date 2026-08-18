"use client";

import { useState } from "react";

import { Button, ButtonLink } from "@/components/button";
import { ExpandingList } from "@/components/expanding-list";
import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { cn } from "@/lib/cn";
import { formatWhen } from "@/lib/outcome";
import { useAlerts, usePreviewAlerts, useSession } from "@/lib/queries";
import type { AlertAction } from "@/lib/types";

const COLLAPSED_LENGTH = 5;
const WINDOW_DAYS = 14;

/**
 * What DeployLens has said out loud, and what it would say next.
 *
 * Alerts are the one thing this product does that writes to somebody else's
 * repository, so the page leads with the rehearsal rather than the act: the
 * preview renders the exact issues a run would open, and nothing is filed until
 * the scheduled sweep runs. Reading before publishing is the whole point.
 */
export function AlertBoard() {
  const session = useSession();
  const signedIn = Boolean(session.data);
  const alerts = useAlerts(signedIn);
  const preview = usePreviewAlerts();

  if (!signedIn) {
    return (
      <Sheet>
        <SheetHead title="Alerts" />
        <Notice
          title="Sign in to see your alerts"
          detail="Alerts are raised on the repositories connected to your GitHub account."
          action={
            <ButtonLink href="/api/auth/github" variant="primary">
              Sign in with GitHub
            </ButtonLink>
          }
        />
      </Sheet>
    );
  }

  const raised = alerts.data ?? [];
  const standing = raised.filter((alert) => !alert.resolved_at);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-rank-b">What got said</h1>
          <span className="label !tracking-[0.1em]">
            {standing.length > 0 ? `${standing.length} standing` : "nothing standing"}
          </span>
        </div>
        <p className="text-ink-quiet max-w-[62ch]">
          A workflow that fails repeatedly, or fails often enough to be untrustworthy, gets an issue
          on the repository it belongs to — and that issue is closed again when the pipeline
          recovers. Nothing else is worth interrupting you for.
        </p>
      </div>

      <Preview
        onRun={() => preview.mutate(WINDOW_DAYS)}
        pending={preview.isPending}
        actions={preview.data?.actions ?? []}
        ran={preview.isSuccess}
        error={preview.error?.message ?? null}
      />

      <Sheet>
        <SheetHead title="Raised" meta={raised.length > 0 ? `${raised.length}` : undefined} />
        {alerts.isPending ? (
          <div className="px-5 py-8" aria-busy="true">
            <span className="bg-rule block h-3 w-44 animate-pulse rounded-[1px]" />
          </div>
        ) : raised.length === 0 ? (
          <Notice
            size="compact"
            title="Nothing has been raised"
            detail="An issue is opened the first time a workflow fails three times running, or fails more than a third of the time over a real sample of runs."
          />
        ) : (
          <ExpandingList items={raised} collapsedLength={COLLAPSED_LENGTH} noun="alerts">
            {(alert) => (
              <li
                key={alert.id}
                className="border-rule grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-1 border-b px-5 py-3.5 last:border-b-0"
              >
                <span className="text-ink truncate font-mono text-[0.8125rem]">
                  {alert.subject}
                </span>
                <span
                  className={cn(
                    "label !tracking-[0.14em]",
                    alert.resolved_at ? "!text-ok" : "!text-hold",
                  )}
                >
                  {alert.resolved_at ? "Recovered" : "Standing"}
                </span>
                <span className="text-ink-quiet text-[0.8125rem]">{alert.detail}</span>
                <span className="label text-right !tracking-[0.08em]">
                  {formatWhen(alert.raised_at)}
                  {alert.issue_url ? (
                    <>
                      {" · "}
                      <a
                        href={alert.issue_url}
                        target="_blank"
                        rel="noreferrer"
                        className="!text-accent decoration-accent/40 hover:decoration-accent underline underline-offset-[3px] transition-colors"
                      >
                        #{alert.issue_number} ↗
                      </a>
                    </>
                  ) : null}
                </span>
              </li>
            )}
          </ExpandingList>
        )}
      </Sheet>
    </div>
  );
}

/**
 * The rehearsal. Every issue the next run would open, rendered exactly as it would
 * be filed — because the only way to know the wording is right is to read it before
 * it is published rather than after.
 */
function Preview({
  onRun,
  pending,
  actions,
  ran,
  error,
}: {
  onRun: () => void;
  pending: boolean;
  actions: AlertAction[];
  ran: boolean;
  error: string | null;
}) {
  const [shown, setShown] = useState<string | null>(null);

  return (
    <Sheet>
      <SheetHead
        title="What would be filed"
        meta={ran ? `${actions.length} · ${WINDOW_DAYS} d` : `${WINDOW_DAYS} d`}
        action={
          <Button onClick={onRun} disabled={pending} size="compact">
            {pending ? "Reading…" : "Check now"}
          </Button>
        }
      />

      {error ? (
        <Notice tone="problem" title="Could not read the projects" detail={error} />
      ) : !ran ? (
        <Notice
          size="compact"
          title="Nothing has been checked yet"
          detail="Reads every connected project and renders the issues it would open. Nothing is sent to GitHub."
        />
      ) : actions.length === 0 ? (
        <Notice
          size="compact"
          title="Nothing worth raising"
          detail={`No workflow is failing repeatedly or failing often across the last ${WINDOW_DAYS} days.`}
        />
      ) : (
        <ul>
          {actions.map((action) => {
            const key = `${action.repository}-${action.subject}-${action.action}`;
            const open = shown === key;
            return (
              <li key={key} className="border-rule border-b last:border-b-0">
                <button
                  type="button"
                  onClick={() => setShown(open ? null : key)}
                  aria-expanded={open}
                  className="hover:bg-sheet-raised grid w-full grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-1 px-5 py-3.5 text-left transition-colors"
                >
                  <span className="text-ink truncate">{action.title}</span>
                  <span
                    className={cn(
                      "label !tracking-[0.14em]",
                      action.action === "resolve" ? "!text-ok" : "!text-hold",
                    )}
                  >
                    {action.action === "resolve" ? "Would close" : "Would open"}
                  </span>
                  <span className="label !tracking-[0.08em]">{action.repository}</span>
                  <span className="label text-right !tracking-[0.08em]">
                    {open ? "hide" : "read it"}
                  </span>
                </button>
                {open ? (
                  <pre className="text-ink-quiet border-rule bg-booth mx-5 mb-4 overflow-x-auto border p-4 font-mono text-[0.75rem] leading-relaxed whitespace-pre-wrap">
                    {action.body}
                  </pre>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </Sheet>
  );
}
