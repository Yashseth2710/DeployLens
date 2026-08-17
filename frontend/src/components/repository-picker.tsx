"use client";

import { useMemo, useState } from "react";

import { Aperture } from "@/components/brand";
import { Button, ButtonLink } from "@/components/button";
import { Notice } from "@/components/notice";
import { Sheet, SheetHead } from "@/components/sheet";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  useAvailableRepositories,
  useConnectRepository,
  useDisconnectRepository,
  useSession,
} from "@/lib/queries";
import type { AvailableRepository } from "@/lib/types";

export function RepositoryPicker() {
  const session = useSession();
  const signedIn = Boolean(session.data);
  const repositories = useAvailableRepositories(signedIn);
  const [filter, setFilter] = useState("");

  const [tracked, untracked] = useMemo(() => {
    const term = filter.trim().toLowerCase();
    const matching = (repositories.data ?? []).filter((repository) =>
      repository.full_name.toLowerCase().includes(term),
    );
    return [
      matching.filter((repository) => repository.connected),
      matching.filter((repository) => !repository.connected),
    ];
  }, [repositories.data, filter]);

  if (session.isPending) {
    return <LoadingSheet title="Repositories" />;
  }

  if (!signedIn) {
    return (
      <Sheet>
        <SheetHead title="Repositories" />
        <Notice
          title="Sign in to choose what DeployLens watches"
          detail="DeployLens reads your GitHub Actions runs, so it needs your authorization before there is anything to show."
          action={
            <ButtonLink href="/api/auth/github" variant="primary">
              Sign in with GitHub
            </ButtonLink>
          }
        />
      </Sheet>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <h1 className="text-rank-b">Choose what goes on press</h1>
        <p className="text-ink-quiet max-w-[62ch]">
          Connecting a repository pulls its recent Actions runs and registers a webhook, so later
          runs arrive on their own. Disconnect at any time; it takes its collected history with it.
        </p>
      </div>

      <Sheet>
        <SheetHead
          title="Your repositories"
          meta={
            repositories.data
              ? `${tracked.length} tracked · ${repositories.data.length} available`
              : undefined
          }
          action={
            repositories.data ? (
              <label className="flex items-center gap-2">
                <span className="sr-only">Filter repositories by name</span>
                <input
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  placeholder="filter by name"
                  className="label border-rule bg-ground focus-visible:border-accent !text-ink w-44 border px-2.5 py-1.5 !tracking-[0.08em] outline-none"
                />
              </label>
            ) : null
          }
        />

        {repositories.isPending ? (
          <PullingRows />
        ) : repositories.error ? (
          <FetchProblem error={repositories.error} onRetry={() => void repositories.refetch()} />
        ) : repositories.data.length === 0 ? (
          <Notice
            title="No repositories came back from GitHub"
            detail="This account has no repositories the granted scopes can see. Create one, or sign in with the account that owns your projects."
          />
        ) : tracked.length + untracked.length === 0 ? (
          <Notice
            title={`Nothing matches “${filter}”`}
            detail="Clear the filter to see them all."
          />
        ) : (
          <div>
            {tracked.length > 0 && <RepositoryGroup label="On press" repositories={tracked} />}
            {untracked.length > 0 && <RepositoryGroup label="Available" repositories={untracked} />}
          </div>
        )}
      </Sheet>
    </div>
  );
}

function RepositoryGroup({
  label,
  repositories,
}: {
  label: string;
  repositories: AvailableRepository[];
}) {
  return (
    <section>
      <h2 className="label border-rule bg-booth border-b px-5 py-2">{label}</h2>
      <ul>
        {repositories.map((repository) => (
          <RepositoryRow key={repository.github_repo_id} repository={repository} />
        ))}
      </ul>
    </section>
  );
}

function RepositoryRow({ repository }: { repository: AvailableRepository }) {
  const connect = useConnectRepository();
  const disconnect = useDisconnectRepository();
  const busy = connect.isPending || disconnect.isPending;
  const failure = connect.error ?? disconnect.error;

  return (
    <li className="border-rule hover:bg-sheet-raised flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b px-5 py-4 transition-colors last:border-b-0">
      <div className="flex min-w-0 flex-col gap-1">
        <span className="flex items-center gap-2.5">
          <span className="text-ink truncate">
            <span className="text-ink-quiet">{repository.owner}/</span>
            {repository.name}
          </span>
          {repository.private && <span className="label !text-ink-faint">private</span>}
        </span>
        <span className="label !tracking-[0.08em]">
          {repository.default_branch}
          {repository.pushed_at ? ` · pushed ${relativeDay(repository.pushed_at)}` : null}
        </span>
        {failure ? (
          <span className="label !text-hold !tracking-[0.08em]">{failure.message}</span>
        ) : null}
      </div>

      <div className="ml-auto flex items-center gap-3">
        {connect.data?.summary ? (
          <span className="label !tracking-[0.08em]">
            {connect.data.summary.runs_added} runs pulled
          </span>
        ) : null}

        {repository.connected ? (
          <Button
            variant="quiet"
            size="compact"
            disabled={busy}
            onClick={() => repository.connected_id && disconnect.mutate(repository.connected_id)}
          >
            {disconnect.isPending ? "Removing…" : "Disconnect"}
          </Button>
        ) : (
          <Button
            variant="secondary"
            size="compact"
            disabled={busy}
            onClick={() => connect.mutate(repository.github_repo_id)}
          >
            {connect.isPending ? (
              <>
                <Aperture spinning className="text-accent" />
                Pulling history…
              </>
            ) : (
              "Connect"
            )}
          </Button>
        )}
      </div>
    </li>
  );
}

function LoadingSheet({ title }: { title: string }) {
  return (
    <Sheet>
      <SheetHead title={title} />
      <PullingRows />
    </Sheet>
  );
}

function PullingRows() {
  return (
    <ul aria-busy="true" aria-label="Loading repositories">
      {[0, 1, 2, 3].map((row) => (
        <li
          key={row}
          className="border-rule flex items-center gap-4 border-b px-5 py-5 last:border-b-0"
        >
          <span
            className={cn("bg-rule h-3 animate-pulse rounded-[1px]")}
            style={{ width: `${9 + row * 3}rem`, animationDelay: `${row * 120}ms` }}
          />
        </li>
      ))}
    </ul>
  );
}

function FetchProblem({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const expired = error instanceof ApiError && error.status === 401;

  return (
    <Notice
      tone="problem"
      title={expired ? "GitHub access expired" : "Could not read your repositories"}
      detail={
        expired
          ? "The stored authorization is no longer valid. Signing in again issues a fresh one."
          : error.message
      }
      action={
        expired ? (
          <ButtonLink href="/api/auth/github" variant="primary">
            Sign in again
          </ButtonLink>
        ) : (
          <Button onClick={onRetry}>Try again</Button>
        )
      }
    />
  );
}

function relativeDay(iso: string): string {
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.round(days / 30);
  return months === 1 ? "a month ago" : `${months} months ago`;
}
