"use client";
import { useState } from "react";
import { Experiment, HistoryRow, ResearchState, signed } from "@/lib/api";

type Props = { history: HistoryRow[]; experiments: Experiment[]; failed: ResearchState["failed_experiments"]; frozenId: string | null; onDetails: (id: string) => void };

function title(h: HistoryRow): string {
  if (h.iteration === 0) return "Baseline · metadata-only logistic regression";
  return (h.change_summary ?? "").split(" (vs")[0].replace(/->/g, "→").replace(/logistic_regression/g, "logistic regression").replace(/^features /, "features ").replace(/^model /, "model ");
}

function firstSentence(s: string | null | undefined, max = 180): string {
  if (!s) return "";
  const m = s.match(/^.*?[.!?](\s|$)/);
  const out = (m ? m[0] : s).trim();
  return out.length > max ? out.slice(0, max - 1).trimEnd() + "…" : out;
}

export default function Journal({ history, experiments, failed, frozenId, onDetails }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const byId = new Map(experiments.map((e) => [e.id, e]));
  const entries = history.slice().reverse();
  const maxScore = Math.max(0.001, ...history.map((h) => h.score));
  return (
    <div className="flex flex-col border-t border-ink">
      {entries.map((h) => {
        const e = byId.get(h.experiment_id);
        const r = e?.result;
        const keep = h.decision === "KEEP";
        const reject = h.decision === "REJECT";
        const frozen = frozenId === h.experiment_id;
        const stampColor = h.iteration === 0 ? "text-ink-2" : reject ? "text-rust" : keep ? "text-teal" : "text-ink-2";
        const stampText = h.iteration === 0 ? "REF" : reject ? "REJECT" : keep ? (frozen ? "FROZEN" : "KEEP") : "…";
        const isOpen = open === h.experiment_id;
        return (
          <div key={h.experiment_id} className="border-b border-rule">
            <button
              className="w-full text-left grid grid-cols-[36px_minmax(0,1fr)_56px_76px] md:grid-cols-[52px_minmax(0,1fr)_220px_80px_84px] items-center gap-3 md:gap-5 py-3.5 cursor-pointer hover:bg-paper-2/60 bg-transparent border-0"
              onClick={() => setOpen(isOpen ? null : h.experiment_id)}
              aria-expanded={isOpen}
              aria-label={`Entry ${h.iteration}: ${title(h)}`}
            >
              <span className="mono text-sm text-ink-2">{String(h.iteration).padStart(2, "0")}</span>
              <span className="flex flex-col gap-0.5 min-w-0">
                <span className="text-[17px] leading-snug font-medium truncate">{title(h)}</span>
                {h.iteration > 0 && <span className="text-[14px] leading-snug italic text-ink-2 truncate">{firstSentence(h.hypothesis, 110)}</span>}
              </span>
              <span className="hidden md:flex items-center gap-2.5">
                <span className="h-1.5 flex-1 bg-paper-2 rounded-[1px] overflow-hidden"><span className={`block h-full ${reject ? "bg-rust" : "bg-teal"}`} style={{ width: `${(h.score / maxScore) * 100}%` }} /></span>
                <span className="mono text-[15px] w-14 text-right">{(h.score * 100).toFixed(1)}</span>
              </span>
              <span className={`mono text-[13px] text-right ${h.delta_vs_previous_best == null ? "text-ink-2" : h.delta_vs_previous_best >= 0 ? "text-teal" : "text-rust"}`}>
                <span className="md:hidden">{(h.score * 100).toFixed(1)}</span>
                <span className="hidden md:inline">{h.delta_vs_previous_best == null ? "—" : signed(h.delta_vs_previous_best).replace(" pts", "")}</span>
              </span>
              <span className={`stamp justify-self-end ${stampColor}`}>{stampText}</span>
            </button>
            {isOpen && (
              <div className="grid grid-cols-1 md:grid-cols-[52px_minmax(0,1fr)] gap-5 pb-5 fade-in">
                <span className="hidden md:block" />
                <div className="flex flex-col gap-3 max-w-[760px]">
                  {h.observation && <p className="text-[15px] leading-relaxed"><span className="runin">Observed</span>{firstSentence(h.observation, 260)}</p>}
                  {h.iteration > 0 && h.hypothesis && <p className="text-[15px] leading-relaxed"><span className="runin">Hypothesis</span>{h.hypothesis}</p>}
                  {h.decision && <p className="text-[15px] leading-relaxed"><span className="runin">Decided</span>{h.decision}. {firstSentence(h.decision_reason, 260)}</p>}
                  {h.next_question && <p className="text-[15px] leading-relaxed italic text-ink-2"><span className="runin">Next</span>{h.next_question}</p>}
                  <div className="ui flex flex-wrap items-center gap-x-5 gap-y-1 text-xs mt-1 text-ink-2">
                    {r && <span className="mono">missed {r.false_negative_count}/{r.val_positives} · false alarms {r.false_positive_count} · AUROC {r.validation_auroc.toFixed(3)} · {r.n_features.toLocaleString()} features · {r.runtime_seconds.toFixed(0)} s</span>}
                    <button className="link cursor-pointer bg-transparent border-0 border-b p-0 text-teal" onClick={() => onDetails(h.experiment_id)} aria-label={`Details for ${h.experiment_id}`}>Full details</button>
                    {h.wandb_run_url && <a className="link" href={h.wandb_run_url} target="_blank" rel="noreferrer">W&amp;B</a>}
                    {h.weave_trace_url && <a className="link" href={h.weave_trace_url} target="_blank" rel="noreferrer">Weave</a>}
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}
      {failed.map((f) => (
        <div key={f.experiment_id} className="grid grid-cols-[52px_minmax(0,1fr)_84px] items-center gap-5 py-3.5 border-b border-rule">
          <span className="mono text-sm text-ink-2">{f.experiment_id.replace("exp-", "")}</span>
          <span className="text-[15px] text-rust truncate">{f.error}</span>
          <span className="stamp justify-self-end text-rust">FAILED</span>
        </div>
      ))}
      {!entries.length && !failed.length && (
        <p className="py-8 text-base italic text-ink-2">No entries yet. Start autonomous research to run the fixed baseline; every later entry is chosen by ARIA.</p>
      )}
    </div>
  );
}
