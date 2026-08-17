import { AppShell } from "@/components/app-shell";
import { Aperture } from "@/components/brand";
import { ButtonLink } from "@/components/button";
import { Reading } from "@/components/reading";
import { Sheet, SheetHead } from "@/components/sheet";
import { ControlBar, SignOff, StepWedge, type Outcome } from "@/components/status";

const SPECIMEN: Outcome[] = [
  "ok",
  "ok",
  "hold",
  "ok",
  "ok",
  "ok",
  "wait",
  "ok",
  "ok",
  "hold",
  "ok",
  "ok",
];

export default function Home() {
  return (
    <AppShell>
      <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,30rem)] lg:gap-14">
        <div className="flex flex-col gap-8 pt-2">
          <h1 className="text-rank-a max-w-[15ch] text-balance">
            Every deploy you pull, on one sheet.
          </h1>

          <p className="text-rank-c text-ink-quiet max-w-[56ch]">
            DeployLens reads the Actions runs across your GitHub projects, separates the ones that
            ship from the ones that only test, and probes the URLs they deploy to. Success rate,
            frequency, duration and uptime — read together, the way a printer reads a press sheet.
          </p>

          <div className="flex flex-col items-start gap-3">
            <ButtonLink href="/api/auth/github" variant="primary">
              Sign in with GitHub
            </ButtonLink>
            <span className="label !tracking-[0.1em]">
              Reads your runs · registers one webhook per connected repository
            </span>
          </div>

          <dl className="border-rule mt-1 grid gap-x-10 gap-y-6 border-t pt-7 sm:grid-cols-3">
            {[
              ["Ingest", "Actions runs, live over webhook"],
              ["Probe", "Deployed URLs, hourly"],
              ["Score", "Delivery and uptime, one number"],
            ].map(([term, detail]) => (
              <div key={term} className="flex flex-col gap-2">
                <dt className="label">{term}</dt>
                <dd className="text-ink-quiet">{detail}</dd>
              </div>
            ))}
          </dl>
        </div>

        <Sheet as="aside" className="w-full lg:sticky lg:top-10">
          <SheetHead title="Specimen sheet" meta="sample data" action={<SignOff outcome="ok" />} />

          <div className="flex flex-col gap-6 px-5 py-5">
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-1">
                <span className="text-rank-c text-ink">octocat/deploylens</span>
                <span className="label">main · 4a91c0f</span>
              </div>
              <StepWedge value={86} />
            </div>

            <div className="flex flex-col gap-2">
              <span className="label">Last 12 deploys</span>
              <ControlBar outcomes={SPECIMEN} />
            </div>

            <div className="border-rule grid grid-cols-2 gap-x-6 gap-y-6 border-t pt-5">
              <Reading label="Success rate" value="83.3" unit="%" sample="30 d · 12 deploys" />
              <Reading label="Uptime" value="99.8" unit="%" sample="30 d · 714 probes" />
              <Reading label="Frequency" value="2.8" unit="/wk" sample="30 d" />
              <Reading label="Median duration" value="3:42" sample="30 d · 12 deploys" />
            </div>

            <p className="label border-rule flex items-center gap-2 border-t pt-4 !tracking-[0.1em]">
              <Aperture className="text-ink-faint" />
              Specimen only — your own projects appear here once connected
            </p>
          </div>
        </Sheet>
      </div>
    </AppShell>
  );
}
