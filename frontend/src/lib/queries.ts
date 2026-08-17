"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import type {
  AvailableRepository,
  ConnectedRepository,
  DeploymentSummary,
  Overview,
  RepositoryDetail,
  SyncSummary,
  UserProfile,
  WorkflowRunRow,
} from "@/lib/types";

export const keys = {
  session: ["session"] as const,
  available: ["repositories", "available"] as const,
  connected: ["repositories", "connected"] as const,
  overview: (days: number) => ["analytics", "overview", days] as const,
  repository: (id: string, days: number) => ["analytics", "repository", id, days] as const,
  deployments: (limit: number, repositoryId?: string) =>
    ["deployments", limit, repositoryId ?? "all"] as const,
  runs: (limit: number, repositoryId?: string) => ["runs", limit, repositoryId ?? "all"] as const,
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

function scoped(limit: number, repositoryId?: string): string {
  const query = new URLSearchParams({ limit: String(limit) });
  if (repositoryId) query.set("repository_id", repositoryId);
  return query.toString();
}
