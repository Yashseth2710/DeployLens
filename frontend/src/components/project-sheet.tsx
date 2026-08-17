import { ButtonLink } from "@/components/button";
import { Reading } from "@/components/reading";
import { Sheet } from "@/components/sheet";
import { ControlBar, SignOff, StepWedge, type Outcome } from "@/components/status";
import { formatDuration, formatWhen, runOutcome } from "@/lib/outcome";
import type { DeploymentSummary, RepositoryMetrics, WorkflowRunRow } from "@/lib/types";

const QUIET_AFTER_DAYS = 14;

/**
 * One project, read the way a printer reads a sheet: the sign-off first, the run
 * of recent impressions along the control bar, then the measurements.
 *
 * The control bar carries every run rather than only the deploys, because most
 * projects have far more CI than releases and a bar built from deploys alone is
 * empty on exactly the repositories that need reading.
 */
export function ProjectSheet({
  metrics,
  latestDeploy,
  runs,
  windowDays,
}: {
  metrics: RepositoryMetrics;
  latestDeploy: DeploymentSummary | null;
  runs: WorkflowRunRow[];
  windowDays: number;
}) {
  const window = `${windowDays} d`;
  const { delivery, pipeline, uptime } = metrics;
  const outcomes: Outcome[] = runs.map((run) => runOutcome(run.status, run.conclusion));
  const latest = runs[0];

  return (
    <Sheet as="article" className="flex flex-col">
      <header className="border-rule flex flex-wrap items-start justify-between gap-x-6 gap-y-3 border-b px-5 py-4">
        <div className="flex min-w-0 flex-col gap-1">
          <a
            href={`https://github.com/${metrics.full_name}`}
            target="_blank"
            rel="noreferrer"
            className="text-rank-c text-ink hover:text-accent truncate transition-colors"
          >
            {metrics.full_name}
          </a>
          <span className="label !tracking-[0.08em]">
            {pipeline.last_run_at
              ? `${activity(pipeline.last_run_at)} · last run ${formatWhen(pipeline.last_run_at)}`
              : "no runs recorded"}
          </span>
        </div>
        <SignOff outcome={latest ? outcomes[0] : "none"} />
      </header>

      <div className="flex flex-col gap-5 px-5 py-5">
        <div className="flex items-end justify-between gap-6">
          <Reading
            label="Health score"
            value={metrics.health_score}
            sample={window}
            absent="nothing measured yet"
          />
          <StepWedge value={metrics.health_score} />
        </div>

        {outcomes.length > 0 ? (
          <div className="flex flex-col gap-2">
            <span className="label">Last {outcomes.length} runs</span>
            <ControlBar outcomes={outcomes} />
          </div>
        ) : null}

        <div className="border-rule grid grid-cols-2 gap-x-6 gap-y-5 border-t pt-5">
          <Reading
            label="Runs passing"
            value={pipeline.success_rate}
            unit="%"
            sample={`${window} · ${pipeline.runs} runs`}
            absent="no runs in window"
          />
          <Reading
            label="Deploys"
            value={delivery.deployments || null}
            sample={
              delivery.deployments
                ? `${delivery.success_rate ?? 0}% clean · ${window}`
                : "no deploy workflow"
            }
            absent="none"
          />
          <Reading
            label="Uptime"
            value={uptime.uptime_percent}
            unit="%"
            sample={
              uptime.monitored_urls > 0 ? `${window} · ${uptime.probes} probes` : "not monitored"
            }
            absent="not monitored"
          />
          <Reading
            label="Average run"
            value={formatDuration(pipeline.average_duration_seconds)}
            sample={`${pipeline.workflows} workflow${pipeline.workflows === 1 ? "" : "s"} · ${pipeline.branches} branch${pipeline.branches === 1 ? "" : "es"}`}
            absent="not timed"
          />
        </div>

        {latestDeploy ? (
          <p className="label border-rule border-t pt-4 !tracking-[0.08em]">
            Last deploy {formatWhen(latestDeploy.started_at)} · {latestDeploy.environment} ·{" "}
            {latestDeploy.status}
          </p>
        ) : null}
      </div>

      <div className="border-rule mt-auto border-t px-5 py-4">
        <ButtonLink href={`/repositories/${metrics.repository_id}`} className="w-full">
          See details
        </ButtonLink>
      </div>
    </Sheet>
  );
}

/**
 * A finished project is not a broken one. Saying so in the header stops a quiet
 * repository reading as a failure to collect anything.
 */
function activity(lastRunAt: string): string {
  const days = (Date.now() - new Date(lastRunAt).getTime()) / 86_400_000;
  return days > QUIET_AFTER_DAYS ? "Quiet" : "Active";
}
