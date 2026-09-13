export type Experiment = {
  id: string;
  session_id: string;
  iteration: number;
  parent_experiment_id: string | null;
  config_key: string;
  status: string;
  controller: string;
  proposal: Record<string, unknown> | null;
  proposal_source: string | null;
  experiment: { model: string; feature_protocol: string; weather_days: number; hyperparameters: Record<string, unknown> };
  change_summary: string | null;
  result: ExperimentResult | null;
  score: number | null;
  previous_best: number | null;
  delta: number | null;
  decision: string | null;
  decision_reason: string | null;
  decision_learning: string | null;
  next_question: string | null;
  decision_source: string | null;
  runtime_seconds: number | null;
  wandb_run_id: string | null;
  wandb_run_url: string | null;
  weave_trace_url: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type Breakdown = { group: string; count: number; positives: number; false_negatives: number; false_positives: number; recall: number | null; small_group: boolean };

export type ExperimentResult = {
  score_kind: string;
  benchmark_comparable: boolean;
  split: string;
  validation_auprc: number;
  validation_auroc: number;
  validation_metrics: Record<string, number>;
  train_auprc: number;
  threshold_best_f1: number;
  confusion_matrix: { tp: number; fp: number; fn: number; tn: number };
  false_negative_count: number;
  false_positive_count: number;
  val_positives: number;
  val_size: number;
  train_size: number;
  n_features: number;
  pr_curve?: { recall: number; precision: number }[];
  feature_importance: { feature: string; importance: number; kind: string }[];
  error_breakdowns: Record<string, Breakdown[]>;
  fit_notes: Record<string, unknown>;
  runtime_seconds: number;
  seed: number;
};

export type Session = {
  id: string;
  status: string;
  aria_mode: string;
  budget: number;
  research_seed: number;
  state_revision: number;
  current_best_experiment_id: string | null;
  current_best_auprc: number | null;
  final_decision: Record<string, string> | null;
  final_evaluation: FinalEvaluation | null;
  error: string | null;
  cancel_requested: boolean;
  wandb_entity: string;
  wandb_project: string;
  created_at: string;
  limit_train_samples: number | null;
  protocol: Record<string, unknown>;
};

export type FinalEvaluation = {
  experiment_id: string;
  mean_test_auprc: number;
  std_test_auprc: number;
  published_test_auprc: number;
  delta_vs_published: number;
  protocol_matched: boolean;
  not_comparable_reasons: string[];
  benchmark_beaten: boolean;
  claim_eligible?: boolean;
  claim_note?: string;
  reported_above_reference?: boolean;
  seeds: number[];
  per_seed: { seed: number; test_auprc: number; val_auprc: number }[];
  wandb_run_url?: string;
  seed_note: string;
};

export type HistoryRow = {
  experiment_id: string;
  iteration: number;
  controller: string;
  experiment: Experiment["experiment"];
  change_summary: string;
  hypothesis: string | null;
  observation: string | null;
  expected_result: string | null;
  reason: string | null;
  score: number;
  previous_best: number | null;
  delta_vs_previous_best: number | null;
  decision: string | null;
  decision_reason: string | null;
  decision_learning: string | null;
  next_question: string | null;
  wandb_run_url: string | null;
  weave_trace_url: string | null;
  runtime_seconds: number | null;
};

export type ResearchState = {
  session_id: string;
  state_revision: number;
  status: string;
  aria_mode: string;
  remaining_budget: number;
  budget: { max_aria_experiments: number; used: number; remaining: number };
  baseline_validation_auprc: number | null;
  current_best_validation_auprc: number | null;
  numeric_best: { experiment_id: string | null; validation_auprc: number | null };
  history: HistoryRow[];
  failed_experiments: { experiment_id: string; error: string; hypothesis: string | null }[];
  pending_experiment: { experiment_id: string; status: string; experiment: Experiment["experiment"]; hypothesis: string | null; observation?: string | null } | null;
  awaiting_decision_for_experiment_id: string | null;
  rejected_messages_at_this_revision: { artifact: string; feedback: { code: string; message: string } }[];
  final_decision: Record<string, string> | null;
};

export type SessionView = {
  session: Session;
  state: ResearchState;
  experiments: Experiment[];
  worker_alive: boolean;
  mode_label: string;
  benchmark: { published_test_auprc: number; published_model: string; beaten: boolean };
  dataset: {
    events_total: number;
    task_events: Record<string, number>;
    positives: Record<string, number>;
    inputs: string[];
    prediction: string;
    constraint: string;
    forbidden: string[];
    provenance: Record<string, unknown>;
    canonical_ready: boolean;
  };
};

export type SessionSummary = { id: string; status: string; aria_mode: string; created_at: string; current_best_auprc: number | null; budget: number; worker_alive: boolean; mode_label: string; benchmark_beaten: boolean };
export type EventRow = { id: number; ts: string; kind: string; message: string; payload: Record<string, unknown> | null };
export type Health = { ok: boolean; aria_mode_default: string; canonical_ready: boolean; wandb_project: string; credential_present: boolean };

async function j<T>(input: string, init?: RequestInit): Promise<T> {
  const r = await fetch(input, { cache: "no-store", ...init });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return r.json();
}

export const api = {
  health: () => j<Health>("/api/health"),
  sessions: () => j<SessionSummary[]>("/api/sessions"),
  session: (id: string) => j<SessionView>(`/api/sessions/${id}`),
  events: (id: string, after = 0) => j<EventRow[]>(`/api/sessions/${id}/events?after=${after}`),
  experiment: (sid: string, eid: string) => j<Experiment>(`/api/sessions/${sid}/experiments/${eid}`),
  start: (body: { budget: number; aria_mode: string; wait_seconds?: number }) => j<SessionView>("/api/sessions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),
  cancel: (id: string) => j<{ ok: boolean }>(`/api/sessions/${id}/cancel`, { method: "POST" }),
  resume: (id: string) => j<SessionView>(`/api/sessions/${id}/resume`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" }),
  replay: (id: string) => j<{ session: Session; state: ResearchState; experiments: Experiment[]; events: EventRow[] }>(`/api/sessions/${id}/replay`),
};

export const pct = (v: number | null | undefined, digits = 1) => (v == null || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(digits)}%`);
export const num = (v: number | null | undefined, digits = 4) => (v == null || Number.isNaN(v) ? "—" : v.toFixed(digits));
export const signed = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)} pts`);
