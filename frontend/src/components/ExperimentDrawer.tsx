"use client";
import { useEffect } from "react";
import { Experiment, num, pct, signed } from "@/lib/api";

export default function ExperimentDrawer({ exp, onClose }: { exp: Experiment; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const r = exp.result;
  const p = (exp.proposal ?? {}) as Record<string, string>;
  const bd = r?.error_breakdowns ?? {};
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink/40" onClick={onClose} role="dialog" aria-modal="true" aria-label={`Experiment ${exp.id} details`}>
      <aside className="h-full w-full max-w-2xl overflow-y-auto bg-paper border-l border-ink p-8 flex flex-col gap-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <span className="cap text-ink">Entry {exp.iteration} · {exp.id} · {exp.controller === "ARIA" ? "chosen by ARIA" : "fixed baseline"}</span>
            <h3 className="text-[26px] font-medium leading-tight m-0">{(exp.change_summary ?? "").replace(/->/g, "→")}</h3>
          </div>
          <button onClick={onClose} className="btn" aria-label="Close details">Close</button>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Stat label="Validation AUPRC" value={pct(exp.score)} />
          <Stat label="Previous best" value={pct(exp.previous_best)} />
          <Stat label="Delta" value={exp.delta == null ? "baseline" : signed(exp.delta)} tone={exp.delta == null ? undefined : exp.delta >= 0 ? "good" : "bad"} />
        </div>
        {r && <p className="ui text-xs text-ink-2">Score kind <span className="mono">{r.score_kind}</span> on {r.split}. {r.score_kind === "DEV_SCORE" ? "Subsampled development run: never comparable to the benchmark." : "Validation scores guide selection; they are not comparable to the published test score."}</p>}

        {p.observation && <p className="text-base leading-relaxed"><span className="runin">Observed</span>{p.observation}</p>}
        {p.hypothesis && <p className="text-base leading-relaxed"><span className="runin">Hypothesis</span>{p.hypothesis}</p>}
        {p.expected_result && <p className="text-base leading-relaxed"><span className="runin">Expected</span>{p.expected_result}</p>}
        {p.reason && <p className="text-base leading-relaxed"><span className="runin">Reason</span>{p.reason}</p>}
        <p className="config">{JSON.stringify(exp.experiment, null, 1).replace(/\n\s*/g, " ")}</p>

        {r && (
          <>
            <div className="grid grid-cols-4 gap-3">
              <Stat label="AUROC" value={num(r.validation_auroc, 3)} />
              <Stat label="Precision" value={num(r.validation_metrics.precision, 3)} />
              <Stat label="Recall" value={num(r.validation_metrics.recall, 3)} />
              <Stat label="F1" value={num(r.validation_metrics.f1, 3)} />
              <Stat label="Recall@5%" value={num(r.validation_metrics.recall_at_5, 3)} />
              <Stat label="Missed escapes" value={`${r.false_negative_count} / ${r.val_positives}`} />
              <Stat label="False alarms" value={String(r.false_positive_count)} />
              <Stat label="Features · runtime" value={`${r.n_features} · ${r.runtime_seconds.toFixed(0)} s`} />
            </div>
            <p className="ui text-xs text-ink-2">Thresholded counts use the official best-F1 validation threshold ({num(r.threshold_best_f1, 2)}). AUPRC is threshold-free; recall and precision trade-offs are not AUPRC improvements.</p>

            {r.feature_importance?.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className="cap">Top features ({r.feature_importance[0].kind})</span>
                <ul className="grid gap-1 text-xs mono">
                  {r.feature_importance.slice(0, 12).map((f) => (
                    <li key={f.feature} className="flex items-center gap-2">
                      <span className="w-56 truncate" title={f.feature}>{f.feature}</span>
                      <span className="h-1.5 bg-teal rounded-[1px]" style={{ width: `${Math.min(100, (Math.abs(f.importance) / Math.abs(r.feature_importance[0].importance)) * 100)}%` }} />
                      <span className="text-ink-2">{f.importance.toFixed(3)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {Object.entries(bd).filter(([, rows]) => rows.length).map(([name, rows]) => (
              <div key={name} className="flex flex-col gap-2">
                <span className="cap">Errors {name.replace(/_/g, " ")} · validation, at threshold</span>
                <table className="w-full text-xs mono">
                  <thead className="text-ink-2"><tr><th className="text-left font-normal pb-1">group</th><th className="font-normal">n</th><th className="font-normal">pos</th><th className="font-normal">missed</th><th className="font-normal">false</th><th className="font-normal">recall</th></tr></thead>
                  <tbody>
                    {rows.slice(0, 6).map((b) => (
                      <tr key={b.group} className={`border-t border-rule ${b.small_group ? "text-ink-2" : ""}`}>
                        <td className="text-left truncate max-w-[200px] py-1">{b.group}{b.small_group ? " (small)" : ""}</td>
                        <td className="text-center">{b.count}</td><td className="text-center">{b.positives}</td><td className="text-center">{b.false_negatives}</td><td className="text-center">{b.false_positives}</td>
                        <td className="text-center">{b.recall == null ? "—" : b.recall.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </>
        )}

        {exp.decision && (
          <div className="border-t border-ink pt-4 flex flex-col gap-2">
            <span className={`stamp ${exp.decision === "KEEP" ? "text-teal" : "text-rust"}`}>{exp.decision}</span>
            <p className="text-base leading-relaxed">{exp.decision_reason}</p>
            {exp.decision_learning && <p className="text-base leading-relaxed"><span className="runin">Learned</span>{exp.decision_learning}</p>}
            {exp.next_question && <p className="text-base leading-relaxed italic text-ink-2"><span className="runin">Next</span>{exp.next_question}</p>}
            {exp.decision_source && <p className="mono text-[11px] text-ink-2">source {exp.decision_source}</p>}
          </div>
        )}
        {exp.error && <p className="text-sm text-rust">{exp.error}</p>}

        <div className="ui flex flex-wrap gap-4 text-xs">
          {exp.wandb_run_url && <a className="link" href={exp.wandb_run_url} target="_blank" rel="noreferrer">W&amp;B run</a>}
          {exp.weave_trace_url && <a className="link" href={exp.weave_trace_url} target="_blank" rel="noreferrer">Weave traces</a>}
          {exp.proposal_source && <span className="mono text-ink-2">proposal {exp.proposal_source}</span>}
        </div>
      </aside>
    </div>
  );
}

export function Stat({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div className="border-t border-ink pt-2 flex flex-col gap-1">
      <div className="cap">{label}</div>
      <div className={`mono text-base ${tone === "good" ? "text-teal" : tone === "bad" ? "text-rust" : "text-ink"}`}>{value}</div>
    </div>
  );
}
