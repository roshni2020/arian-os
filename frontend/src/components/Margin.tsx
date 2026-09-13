"use client";
import { EventRow, FinalEvaluation, SessionView } from "@/lib/api";

type Props = { view: SessionView; finalEval: FinalEvaluation | null; events: EventRow[]; hideLog: boolean };

function Fold({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <details className="group border-t border-rule py-3">
      <summary className="cap cursor-pointer list-none flex items-center justify-between text-ink hover:text-teal">
        {label}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-open:rotate-180" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </summary>
      <div className="pt-3 flex flex-col gap-2">{children}</div>
    </details>
  );
}

/** Seeds, caveats, dataset and log: everything secondary lives here, folded by default. */
export default function Margin({ view, finalEval, events, hideLog }: Props) {
  const d = view.dataset;
  const s = view.session;
  const wb = `https://wandb.ai/${s.wandb_entity}/${s.wandb_project}`;
  const log = hideLog ? [] : events.slice(-30).reverse();
  const seeds = finalEval?.per_seed ?? [];
  const lo = seeds.length ? Math.min(...seeds.map((p) => p.test_auprc)) : 0;
  const hi = seeds.length ? Math.max(...seeds.map((p) => p.test_auprc)) : 1;
  return (
    <section className="grid grid-cols-1 lg:grid-cols-2 gap-x-16">
      <div className="flex flex-col">
        {finalEval && (
          <div className="border-t border-rule py-3 flex flex-col gap-3">
            <span className="cap text-ink">Final evaluation · {finalEval.seeds.length} seeds on the sealed 2020 test year</span>
            <div className="flex items-end gap-3 h-16">
              {seeds.map((p) => {
                const rel = hi === lo ? 1 : 0.35 + 0.65 * ((p.test_auprc - lo) / (hi - lo));
                return (
                  <div key={p.seed} className="flex-1 flex flex-col items-center gap-1 h-full justify-end">
                    <span className="mono text-xs">{(p.test_auprc * 100).toFixed(2)}</span>
                    <span className="w-full bg-teal rounded-[1px]" style={{ height: `${rel * 36}px` }} />
                    <span className="mono text-[10px] text-ink-2">{p.seed}</span>
                  </div>
                );
              })}
            </div>
            <span className="ui text-xs text-ink-2">mean {(finalEval.mean_test_auprc * 100).toFixed(2)} · std {(finalEval.std_test_auprc * 100).toFixed(2)} pts · {finalEval.protocol_matched ? "protocol-matched" : `not comparable: ${finalEval.not_comparable_reasons.join("; ")}`}{finalEval.wandb_run_url && <> · <a className="link" href={finalEval.wandb_run_url} target="_blank" rel="noreferrer">run</a></>}</span>
          </div>
        )}
        <Fold label="Caveats">
          {finalEval?.claim_note && <p className="ui text-xs leading-relaxed text-ink-2">{finalEval.claim_note}</p>}
          {finalEval?.seed_note && <p className="ui text-xs leading-relaxed text-ink-2">{finalEval.seed_note}</p>}
          <p className="ui text-xs leading-relaxed text-ink-2">Validation AUPRC on 2019 is the selection metric. Only the one-time test evaluation of a frozen configuration compares with the published number.</p>
          <p className="ui text-xs leading-relaxed text-ink-2">ARIA&apos;s reasoning runs in W&amp;B&apos;s environment and is not traced. Its observations, hypotheses and decisions are received outputs, verbatim.</p>
        </Fold>
      </div>
      <div className="flex flex-col">
        <div className="border-t border-rule py-3 flex flex-col gap-2">
          <span className="cap text-ink">Dataset · WildfireIA</span>
          <div className="grid grid-cols-4 gap-3">
            <Num v={d.events_total.toLocaleString()} l="events" />
            <Num v={d.task_events.train_2016_2018.toLocaleString()} l="train 2016–18" />
            <Num v={d.task_events.val_2019.toLocaleString()} l="val 2019" />
            <Num v={d.task_events.test_2020.toLocaleString()} l="test 2020" />
          </div>
          <span className="ui text-xs text-ink-2">Discovery-day inputs only. Leakage columns removed by the official loader. <span className="mono">repo {String(d.provenance.pinned_commit).slice(0, 8)} · data {String(d.provenance.dataset_revision).slice(0, 8)}</span></span>
        </div>
        <Fold label={`Log · ${events.length} events`}>
          <ul className="mono text-[11px] leading-relaxed flex flex-col gap-0.5 max-h-48 overflow-y-auto">
            {log.map((e) => (
              <li key={e.id} className={e.kind.includes("fail") || e.kind.includes("reject") || e.kind === "traceback" ? "text-rust" : e.kind.startsWith("aria") || e.kind === "final_decision" ? "text-teal" : "text-ink-2"}>
                <span className="text-ink-2">{e.ts.slice(11, 19)}</span> {e.message}
              </li>
            ))}
            {!log.length && <li className="text-ink-2 italic">{hideLog ? "Appears when the replay finishes." : "no events yet"}</li>}
          </ul>
        </Fold>
        <div className="ui flex flex-wrap gap-5 text-xs pt-3 border-t border-rule">
          <a className="link" href={wb} target="_blank" rel="noreferrer">W&amp;B project</a>
          <a className="link" href={`${wb}/weave/traces`} target="_blank" rel="noreferrer">Weave traces</a>
        </div>
      </div>
    </section>
  );
}

function Num({ v, l }: { v: string; l: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="mono text-lg leading-none">{v}</span>
      <span className="cap text-[10px]">{l}</span>
    </div>
  );
}
