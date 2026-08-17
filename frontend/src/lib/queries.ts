"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type {
  ActivityBoard,
  AvailableRepository,
  ConnectedRepository,
  DeploymentSummary,
  Overview,
  PullRequestRow,
  RepositoryDetail,
  SyncSummary,
  UserProfile,
  WorkflowRunRow,
} from "@/lib/types";

// The first ask happens before the server has said how often to come back.
const FIRST_POLL_MS = 10_000;

export const keys = {
  session: ["session"] as const,
  activity: ["activity"] as const,
  available: ["repositories", "available"] as const,
  connected: ["repositories", "connected"] as const,
  overview: (days: number) => ["analytics", "overview", days] as const,
  repository: (id: string, days: number) => ["analytics", "repository", id, days] as const,
  deployments: (limit: number, repositoryId?: string) =>
    ["deployments", limit, repositoryId ?? "all"] as const,
  runs: (limit: number, repositoryId?: string) => ["runs", limit, repositoryId ?? "all"] as const,
  pullRequests: (limit: number, repositoryId?: string) =>
    ["pull-requests", limit, repositoryId ?? "all"] as const,
};

export function useSession() {
  return useQuery({
    queryKey: keys.session,
    queryFn: () => api<UserProfile>("/api/auth/me"),
    // A 401 is the answer, not a failure to retry: it means signed out.
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
    staleTime: 5 * 60 * 1000,
  });
}

export function useAvailableRepositories(enabled: boolean) {
  return useQuery({
    queryKey: keys.available,
    queryFn: () => api<AvailableRepository[]>("/api/repositories/available"),
    enabled,
    // Each call spends GitHub rate limit, so a revisit inside a minute reuses it.
    staleTime: 60 * 1000,
    retry: false,
  });
}

export function useConnectedRepositories(enabled: boolean) {
  return useQuery({
    queryKey: keys.connected,
    queryFn: () => api<ConnectedRepository[]>("/api/repositories"),
    enabled,
    retry: false,
  });
}

/**
 * Connecting is two calls, deliberately: the repository is recorded first, then
 * its history is pulled. A sync that fails still leaves the repository connected
 * and syncable, rather than rolling back a connection the user asked for.
 */
export function useConnectRepository() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: async (githubRepoId: number) => {
      const repository = await api<ConnectedRepository>("/api/repositories", {
        method: "POST",
        body: JSON.stringify({ github_repo_id: githubRepoId }),
      });
      const summary = await api<SyncSummary>(`/api/repositories/${repository.id}/sync`, {
        method: "POST",
      }).catch(() => null);
      return { repository, summary };
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export function useDisconnectRepository() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: (repositoryId: string) =>
      api<void>(`/api/repositories/${repositoryId}`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export function useSignOut() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: () => api<void>("/api/auth/logout", { method: "POST" }),
    onSuccess: () => client.clear(),
  });
}

/**
 * The loop that makes the product current. Asking for the board is what triggers
 * the pull, so there is nothing to press; the server sets the interval, because it
 * is the same number as the throttle it applies and the two must not drift.
 *
 * Everything downstream is invalidated whenever a pull actually brought
 * something back, so the dashboard's numbers move with the board rather than
 * lagging a page load behind it.
 */
export function useActivityBoard(enabled: boolean) {
  const client = useQueryClient();
  const [poll, setPoll] = useState(FIRST_POLL_MS);

  const board = useQuery({
    queryKey: keys.activity,
    queryFn: async () => {
      const next = await api<ActivityBoard>("/api/activity", { method: "POST" });
      setPoll(next.poll_seconds * 1000);
      return next;
    },
    enabled,
    retry: false,
    refetchInterval: poll,
    // A tab left open in the background should not keep waking the database.
    refetchIntervalInBackground: false,
  });

  const brought = board.data?.synced ?? 0;
  useEffect(() => {
    if (brought > 0) {
      void client.invalidateQueries({ queryKey: ["analytics"] });
      void client.invalidateQueries({ queryKey: ["runs"] });
      void client.invalidateQueries({ queryKey: ["deployments"] });
      void client.invalidateQueries({ queryKey: ["pull-requests"] });
    }
  }, [brought, client, board.dataUpdatedAt]);

  return board;
}

/**
 * A 401 from the board means the stored GitHub token was revoked or expired — the
 * session is still fine, which is why this is distinct from being signed out.
 */
export function isAccessExpired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/**
 * Reads the board another component is already polling, without starting a second
 * loop of its own. The navigation wants the count, not the responsibility.
 */
export function useLiveCount(): number {
  const { data } = useQuery({
    queryKey: keys.activity,
    queryFn: () => api<ActivityBoard>("/api/activity", { method: "POST" }),
    enabled: false,
  });
  return data?.live_count ?? 0;
}

export function useOverview(days: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.overview(days),
    queryFn: () => api<Overview>(`/api/analytics/overview?days=${days}`),
    enabled,
    retry: false,
  });
}

/**
 * One request for every repository's recent deploys, grouped on the client. The
 * alternative is a request per project, and the dashboard would then wake the
 * database once per card.
 */
export function useRecentDeployments(limit: number, enabled: boolean, repositoryId?: string) {
  return useQuery({
    queryKey: keys.deployments(limit, repositoryId),
    queryFn: () => api<DeploymentSummary[]>(`/api/deployments?${scoped(limit, repositoryId)}`),
    enabled,
    retry: false,
  });
}

/**
 * One repository read on its own, with the workflow and branch breakdowns that
 * only mean anything at this scale.
 */
export function useRepositoryDetail(repositoryId: string, days: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.repository(repositoryId, days),
    queryFn: () =>
      api<RepositoryDetail>(`/api/analytics/repositories/${repositoryId}?days=${days}`),
    enabled,
    retry: false,
  });
}

/**
 * Every Actions run, not only the ones that shipped. This is what the activity
 * feed reads: a failing test on a pull request is delivery information too.
 */
export function useRecentRuns(limit: number, enabled: boolean, repositoryId?: string) {
  return useQuery({
    queryKey: keys.runs(limit, repositoryId),
    queryFn: () => api<WorkflowRunRow[]>(`/api/runs?${scoped(limit, repositoryId)}`),
    enabled,
    retry: false,
  });
}

/**
 * Pull requests carry the one thing runs cannot say: whether the work was merged
 * or abandoned. GitHub calls both of those "closed", so the distinction is made
 * here and not read off a state field.
 */
export function usePullRequests(limit: number, enabled: boolean, repositoryId?: string) {
  return useQuery({
    queryKey: keys.pullRequests(limit, repositoryId),
    queryFn: () => api<PullRequestRow[]>(`/api/pull-requests?${scoped(limit, repositoryId)}`),
    enabled,
    retry: false,
  });
}

function scoped(limit: number, repositoryId?: string): string {
  const query = new URLSearchParams({ limit: String(limit) });
  if (repositoryId) query.set("repository_id", repositoryId);
  return query.toString();
}
