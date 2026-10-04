export type Outcome =
  | "pr_draft" | "pr_ready" | "shadow_ok" | "blocked" | "no_fix" | "verify_failed" | "error" | "skipped";

export interface RunSummary {
  id: string;
  created_at: number;
  service: string;
  title: string;
  status: "queued" | "running" | "done";
  outcome: Outcome | null;
  reason: string | null;
  mode: string | null;
  runner: string | null;
  attempts: number;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  duration_ms: number | null;
  occurrences: number;
  feedback: "accepted" | "rejected" | null;
}

export interface Span {
  id: string;
  parent_id: string | null;
  name: string;
  start_ms: number;
  end_ms: number;
  status: "ok" | "error";
  attrs: Record<string, unknown>;
}

export interface Violation { rule: string; severity: "block" | "warn"; detail: string }
export interface ToolCall { tool: string; path?: string | null; command?: string | null; ok: boolean | null }
export interface Attempt {
  attempt: number; ok: boolean; text: string; model: string | null; duration_ms: number | null;
  tokens_in: number | null; tokens_out: number | null; tool_calls: ToolCall[]; error: string | null; timed_out: boolean;
}
export interface Verification { new_tests: string[]; repro: string; suite_passed: boolean; suite_output: string }

export interface RunDetail extends RunSummary {
  spans: Span[];
  diff: string | null;
  pr_body: string | null;
  branch: string | null;
  pr_url: string | null;
  error: string | null;
  prompt_version: string | null;
  feedback_note: string | null;
  guardrails: Violation[] | null;
  verify: Verification | null;
  agent: Attempt[] | null;
  incident: { exception: { type: string; value: string; frames: { filename: string; lineno: number; function: string }[] }; environment: string; release: string | null };
}

export interface StageStat { count: number; p50_ms: number | null; p95_ms: number | null }
export interface Stats {
  runs: number; attempted: number; outcomes: Record<string, number>; guardrail_rules: Record<string, number>;
  fix_rate: number | null; prs_opened: number; accept_rate: number | null; reviewed: number; occurrences_covered: number;
  p50_time_to_fix_ms: number | null; p95_time_to_fix_ms: number | null; tokens_in: number; tokens_out: number;
  cost_usd: number | null; cost_per_fix_usd: number | null; stages: Record<string, StageStat>;
}

export interface Policy { service: string; mode: string; sample_pct: number; breaker: { open: boolean; bad: number; window: number } }
export interface Rollout { kill_switch: boolean; modes: string[]; services: Policy[] }

export interface EvalCase {
  case: string; run_id: string; outcome: string; reason: string | null; heldout: boolean | null; label: string;
  expected: string | null; matches_expected: boolean | null; attempts: number; duration_ms: number | null; cost_usd: number | null;
}
export interface EvalRun {
  id: string; created_at: number; runner: string; prompt_version: string; cases: EvalCase[];
  summary: {
    cases: number; labels: Record<string, number>; resolve_rate: number; false_fix_rate: number; precision: number | null;
    p50_ms: number | null; p95_ms: number | null; total_cost_usd: number | null; cost_per_resolved_usd: number | null;
    passed: boolean; failures: string[];
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { "content-type": "application/json", ...init?.headers } });
  if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 200)}`);
  return res.json() as Promise<T>;
}
const put = (body: unknown): RequestInit => ({ method: "PUT", body: JSON.stringify(body) });
const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<{ ok: boolean; runner: string; services: string[] }>("/healthz"),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  stats: () => request<Stats>("/api/stats"),
  rollout: () => request<Rollout>("/api/rollout"),
  setPolicy: (service: string, mode: string, sample_pct: number) => request<Policy>(`/api/rollout/${service}`, put({ mode, sample_pct })),
  setKill: (on: boolean) => request<{ kill_switch: boolean }>("/api/rollout/kill-switch", put({ on })),
  evals: () => request<EvalRun[]>("/api/evals"),
  startEval: () => request<{ started: boolean }>("/api/evals/run", post({})),
  feedback: (id: string, verdict: "accepted" | "rejected", note: string) => request<{ ok: boolean }>(`/api/runs/${id}/feedback`, post({ verdict, note })),
};
