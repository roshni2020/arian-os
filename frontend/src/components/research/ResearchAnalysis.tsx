"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Experiment } from "@/lib/api";
import { acceptAnalysisRecord, analysisCacheKey, analysisRecordForView, cachedAnalysisRecord, resolveAnalysisSelection } from "@/lib/research-analysis";
import { Notice } from "../benchmarks/BenchmarkShell";
import ExperimentComparison from "./ExperimentComparison";
import ErrorAnalysis from "./ErrorAnalysis";
import AssistantWorkspace from "./AssistantWorkspace";

export default function ResearchAnalysis({ sessionId, experiments, kind, enabled, replay = false, onInspect }: { sessionId: string; experiments: Experiment[]; kind: "compare" | "errors"; enabled: boolean; replay?: boolean; onInspect: (id: string) => void }) {
  const scope = `${sessionId}:${replay ? "replay" : "live"}`;
  const [selection, setSelection] = useState({ scope, pinnedId: "", candidateId: "" });
  const pinnedId = selection.scope === scope ? selection.pinnedId : "";
  const candidateId = selection.scope === scope ? selection.candidateId : "";
  const [details, setDetails] = useState<Record<string, Experiment>>({});
  const cache = useRef<Record<string, Experiment>>({});
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const [assistantFocus, setAssistantFocus] = useState<{kind: "ask" | "error_proposal"; group?: {dimension: string; group: string}} | null>(null);
  const { available, baseline: baselineInput, candidate: candidateInput } = resolveAnalysisSelection(experiments, sessionId, pinnedId, candidateId);
  const requests = JSON.stringify([baselineInput, candidateInput].filter((exp): exp is Experiment => !!exp).map(exp => ({ id: exp.id, updated_at: exp.updated_at })));
  const fetchKey = `${scope}:${requests}:${retry}`;

  useEffect(() => {
    if (replay || !enabled || requests === "[]") return;
    let active = true;
    const targets = (JSON.parse(requests) as { id: string; updated_at: string }[]).filter(target => {
      const existing = cache.current[analysisCacheKey(sessionId, target.id)];
      return !existing || !acceptAnalysisRecord(existing, { ...target, session_id: sessionId });
    });
    if (!targets.length) return;
    Promise.allSettled(targets.map(target => api.experiment(sessionId, target.id))).then(results => {
      if (!active) return;
      const received: Record<string, Experiment> = {};
      const failed: string[] = [];
      results.forEach((result, index) => {
        if (result.status === "fulfilled" && acceptAnalysisRecord(result.value, { ...targets[index], session_id: sessionId })) received[analysisCacheKey(sessionId, result.value.id)] = result.value;
        else failed.push(targets[index].id);
      });
      cache.current = { ...cache.current, ...received };
      setDetails(cache.current);
      setFailure(failed.length ? { key: fetchKey, message: `Full records for ${failed.join(", ")} could not be loaded. Showing the saved summaries; unavailable curves remain empty.` } : null);
    });
    return () => { active = false; };
  }, [sessionId, requests, fetchKey, replay, enabled]);

  function fullRecord(exp: Experiment | null): Experiment | null {
    return analysisRecordForView(exp, sessionId, details, replay);
  }
  const loading = enabled && !replay && [baselineInput, candidateInput].some(exp => exp && !cachedAnalysisRecord(exp, sessionId, details)) && failure?.key !== fetchKey;
  const baseline = fullRecord(baselineInput);
  const candidate = fullRecord(candidateInput);
  function swap() {
    if (baselineInput && candidateInput) setSelection({ scope, pinnedId: candidateInput.id, candidateId: baselineInput.id });
  }

  return <div className="space-y-5">
    <section className="surface p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="section-title">{kind === "compare" ? "Compare experiments" : "Analyze validation errors"}</h2><p className="mt-1 text-xs leading-5 text-ink-2">Choose a baseline and a candidate from this session. Your baseline stays fixed as you inspect other candidates.</p></div>{replay && <span className="status-badge">Stored replay</span>}</div>
      {available.length || pinnedId || candidateId ? <div className="mt-5 grid items-end gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <label className="flex min-w-0 flex-col gap-2 text-xs font-medium"><span className="inline-flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-ink-2" />Pinned baseline</span><select className="form-control" value={pinnedId || baselineInput?.id || ""} onChange={event => setSelection({ scope, pinnedId: event.target.value, candidateId: candidateInput?.id === event.target.value ? baselineInput?.id || "" : candidateId })} disabled={!available.length} aria-label="Pinned baseline">{pinnedId && !baselineInput && <option value={pinnedId} disabled>{pinnedId} · Not available in this view</option>}{available.map(exp => <option key={exp.id} value={exp.id}>{exp.id} · {exp.change_summary || exp.experiment.model}</option>)}</select></label>
        <button className="btn" onClick={swap} disabled={!baselineInput || !candidateInput} aria-label="Swap baseline and candidate">⇄ <span className="md:sr-only">Swap</span></button>
        <label className="flex min-w-0 flex-col gap-2 text-xs font-medium"><span className="inline-flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-teal" />Candidate</span><select className="form-control" value={candidateId || candidateInput?.id || ""} onChange={event => setSelection({ scope, pinnedId, candidateId: event.target.value })} disabled={!available.some(exp => exp.id !== baselineInput?.id)} aria-label="Comparison candidate">{candidateId && !candidateInput ? <option value={candidateId} disabled>{candidateId} · Not available in this view</option> : !candidateInput && <option value="">No second result yet</option>}{available.filter(exp => exp.id !== baselineInput?.id).map(exp => <option key={exp.id} value={exp.id}>{exp.id} · {exp.change_summary || exp.experiment.model}</option>)}</select></label>
      </div> : <p className="mt-5 text-sm text-ink-2">No recorded results yet. Completed experiments will appear here.</p>}
      {((pinnedId && !baselineInput) || (candidateId && !candidateInput)) && <p role="status" className="mt-3 text-xs leading-5 text-ink-2">Your selected {pinnedId && !baselineInput ? "baseline" : "candidate"} is not available in this view. {replay ? "Advance the replay or choose another recorded experiment." : "Choose another recorded experiment or wait for the session to update."}</p>}
      {loading && <p role="status" className="mt-3 text-xs text-ink-2">Loading full experiment records…</p>}
      <div className="mt-4 flex flex-wrap gap-2"><button className="btn btn-primary" onClick={() => setAssistantFocus({kind:"ask"})}>Ask ARIA about these runs</button><button className="btn" onClick={() => setAssistantFocus({kind:"error_proposal"})}>Propose an experiment</button>{assistantFocus && <button className="btn" onClick={() => setAssistantFocus(null)}>Close ARIA tools</button>}</div>
    </section>
    {enabled && assistantFocus && <div id="aria-analysis"><AssistantWorkspace key={JSON.stringify([scope,assistantFocus])} sessionId={sessionId} experimentIds={[baselineInput?.id,candidateInput?.id].filter((id):id is string=>!!id)} initialKind={assistantFocus.kind} group={assistantFocus.group} replay={replay} /></div>}
    {failure?.key === fetchKey && <Notice error>{failure.message} <button className="underline" onClick={() => setRetry(n => n + 1)}>Retry</button></Notice>}
    {kind === "compare" ? <ExperimentComparison baseline={baseline} candidate={candidate} onInspect={onInspect} /> : <ErrorAnalysis baseline={baseline} candidate={candidate} onInspect={onInspect} onPropose={(dimension,group) => { setAssistantFocus({kind:"error_proposal",group:{dimension,group}}); setTimeout(()=>document.getElementById("aria-analysis")?.scrollIntoView({block:"start"}),0); }} />}
  </div>;
}
