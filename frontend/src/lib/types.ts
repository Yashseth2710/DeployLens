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
  provider_deployments: number;
};

export type DeploymentSummary = {
  id: string;
  repository_id: string;
  repository_full_name: string;
  environment: string;
  status: string;
  branch: string | null;
  commit_sha: string | null;
  author: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  deployment_url: string | null;
};

export type DeliveryMetrics = {
  deployments: number;
  succeeded: number;
  failed: number;
  success_rate: number | null;
  average_duration_seconds: number | null;
  deployments_per_week: number;
  last_deployment_at: string | null;
};

export type UptimeMetrics = {
  monitored_urls: number;
  probes: number;
  up: number;
  uptime_percent: number | null;
  average_response_time_ms: number | null;
};

export type HealthCheck = {
  id: string;
  repository_id: string;
  url: string;
  interval_minutes: number;
  expected_status: number;
  enabled: boolean;
  created_at: string;
};

export type HealthResult = {
  id: string;
  health_check_id: string;
  status: "up" | "down";
  status_code: number | null;
  response_time_ms: number | null;
  error_message: string | null;
  checked_at: string;
};

export type PipelineMetrics = {
  runs: number;
  succeeded: number;
  failed: number;
  success_rate: number | null;
  average_duration_seconds: number | null;
  workflows: number;
  branches: number;
  last_run_at: string | null;
};

export type WorkflowRunRow = {
  id: string;
  repository_id: string;
  repository_full_name: string;
  github_run_id: number;
  workflow_name: string;
  branch: string | null;
  commit_sha: string | null;
  status: string;
  conclusion: string | null;
  event: string | null;
  actor: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  html_url: string | null;
};

export type RepositoryMetrics = {
  repository_id: string;
  full_name: string;
  delivery: DeliveryMetrics;
  pipeline: PipelineMetrics;
  uptime: UptimeMetrics;
  health_score: number | null;
};

export type ActivityItem = {
  kind: "run" | "deploy";
  id: string;
  repository_id: string;
  repository_full_name: string;
  title: string;
  detail: string | null;
  status: string;
  conclusion: string | null;
  live: boolean;
  started_at: string | null;
  completed_at: string | null;
  url: string | null;
};

export type ActivityBoard = {
  items: ActivityItem[];
  live_count: number;
  last_synced_at: string | null;
  synced: number;
  failed: number;
  poll_seconds: number;
};

export type ReviewMetrics = {
  opened: number;
  merged: number;
  closed_unmerged: number;
  open_now: number;
  merge_rate: number | null;
  median_hours_to_merge: number | null;
  commits: number;
  commits_per_week: number;
  first_commit_week: string | null;
};

export type PullRequestRow = {
  id: string;
  repository_id: string;
  repository_full_name: string;
  number: number;
  title: string;
  author: string | null;
  outcome: "open" | "merged" | "abandoned";
  draft: boolean;
  head_branch: string | null;
  base_branch: string | null;
  html_url: string | null;
  opened_at: string | null;
  merged_at: string | null;
  closed_at: string | null;
};

export type RunGroup = {
  name: string;
  runs: number;
  succeeded: number;
  failed: number;
  success_rate: number | null;
  average_duration_seconds: number | null;
  last_run_at: string | null;
};

export type RepositoryDetail = {
  repository: ConnectedRepository;
  window_days: number;
  delivery: DeliveryMetrics;
  pipeline: PipelineMetrics;
  uptime: UptimeMetrics;
  review: ReviewMetrics;
  health_score: number | null;
  workflows: RunGroup[];
  branches: RunGroup[];
  first_activity_at: string | null;
};

export type FindingKind = "streak" | "flaky" | "chronic" | "branch" | "slowdown";

export type Finding = {
  kind: FindingKind;
  subject: string;
  detail: string;
  runs: number;
  failed: number;
  last_seen_at: string | null;
  run_url: string | null;
};

export type RepositoryFindings = {
  repository_id: string;
  full_name: string;
  findings: Finding[];
};

export type Insights = {
  window_days: number;
  findings: Finding[];
};

export type Attention = {
  window_days: number;
  repositories: RepositoryFindings[];
};

export type Overview = {
  window_days: number;
  connected_repositories: number;
  delivery: DeliveryMetrics;
  pipeline: PipelineMetrics;
  uptime: UptimeMetrics;
  review: ReviewMetrics;
  health_score: number | null;
  repositories: RepositoryMetrics[];
};
