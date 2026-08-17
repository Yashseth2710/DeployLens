"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import type {
  AvailableRepository,
  ConnectedRepository,
  SyncSummary,
  UserProfile,
} from "@/lib/types";

export const keys = {
  session: ["session"] as const,
  available: ["repositories", "available"] as const,
  connected: ["repositories", "connected"] as const,
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
