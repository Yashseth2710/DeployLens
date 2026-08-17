export type UserProfile = {
  id: string;
  github_id: number;
  username: string;
  email: string | null;
  avatar_url: string | null;
};

export type ConnectedRepository = {
  id: string;
  github_repo_id: number;
  name: string;
  full_name: string;
  owner: string;
  default_branch: string;
  github_url: string;
  connected_at: string;
};

export type AvailableRepository = {
  github_repo_id: number;
  name: string;
  full_name: string;
  owner: string;
  default_branch: string;
  github_url: string;
  private: boolean;
  pushed_at: string | null;
  connected: boolean;
  connected_id: string | null;
};

export type SyncSummary = {
  runs_seen: number;
  runs_added: number;
  deployments_added: number;
};
