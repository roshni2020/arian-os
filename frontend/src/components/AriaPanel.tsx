"use client";
import { ResearchState, Session } from "@/lib/api";

type Props = { session: Session; state: ResearchState; live: boolean };

const STATUS_TEXT: Record<string, string> = {
  created: "Ready",
  running_baseline: "Running the fixed baseline",
  awaiting_aria_proposal: "Waiting for ARIA's next proposal",
  validating_proposal: "Validating ARIA's proposal",
  training: "Training",
  evaluating: "Evaluating on the 2019 validation year",
  awaiting_final_decision: "Waiting for ARIA's final decision",
  final_evaluation: "Official test evaluation running",
  complete: "Complete",
  cancelled: "Cancelled",
  error: "Error",
};

const ACTIVE = new Set(["running_baseline", "awaiting_aria_proposal", "validating_proposal", "training", "evaluating", "awaiting_final_decision", "final_evaluation"]);

function hp(h: Record<string, unknown>): string {
  const entries = Object.entries(h ?? {});
  return entries.map(([k, v]) => `${k} ${v === null ? "null" : String(v)}`).join(" · ");
}

/** Slim status band: only visible while something is happening or wrong. */
export default function AriaPanel({ session, state, live }: Props) {
  const pending = state.pending_experiment;
  const rejected = state.rejected_messages_at_this_revision[0];
  const active = ACTIVE.has(session.status);
  if (!(active || pending || session.error || session.aria_mode === "fallback" || rejected)) return null;
  const tone = session.error || rejected || session.aria_mode === "fallback" ? "border-rust" : "border-teal";
  return (
    <div className={`ui flex flex-col gap-1.5 border-l-2 ${tone} pl-4 py-1 mb-6`} aria-live="polite">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        {live && active && <span className="live-dot inline-block h-2 w-2 rounded-full bg-teal" />}
        <span className="font-medium">{STATUS_TEXT[session.status] ?? session.status}</span>
        <span className="text-ink-2">r{state.state_revision} · {state.remaining_budget} of {state.budget.max_aria_experiments} experiments remaining</span>
      </div>
      {session.aria_mode === "fallback" && <span className="text-sm text-rust">Development fallback: a scripted stub is driving this session, not ARIA.</span>}
      {session.error && <span className="text-sm text-rust">{session.error}</span>}
      {rejected && <span className="text-sm text-rust">Proposal rejected ({rejected.feedback.code}): {rejected.feedback.message}. Feedback published, waiting for a corrected proposal.</span>}
      {pending && (
        <span className="mono text-xs text-ink-2 truncate">{pending.experiment_id} · {pending.experiment.model} · {pending.experiment.feature_protocol} · w{pending.experiment.weather_days}{Object.keys(pending.experiment.hyperparameters ?? {}).length ? " · " + hp(pending.experiment.hyperparameters) : ""}</span>
      )}
      {pending?.hypothesis && <span className="text-sm italic text-ink-2 font-serif">{pending.hypothesis}</span>}
    </div>
  );
}
