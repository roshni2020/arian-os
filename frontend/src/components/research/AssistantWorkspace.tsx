"use client";

import { useEffect, useRef, useState } from "react";
import { assistantApi, errorText, pendingRequest, scopeQuery, submissionKey, type AssistantKind, type AssistantRequest, type Capabilities } from "@/lib/assistant";
import AssistantTools from "./AssistantTools";

export type AssistantWorkspaceProps = { sessionId?: string; projectId?: string; experimentIds?: string[]; initialKind?: AssistantKind; group?: { dimension: string; group: string }; replay?: boolean };
const labels: Record<AssistantKind, string> = { ask: "Ask ARIA", error_proposal: "Propose an experiment", study_plan: "Plan a study", report: "Research report" };
const prompts: Record<AssistantKind, string> = { ask: "What changed between these experiments, and what evidence supports the improvement?", error_proposal: "Propose one experiment to investigate this error group. Include a hypothesis, expected benefit, tradeoffs, and success criteria.", study_plan: "Draft a bounded study with the fixed baseline, experiment strategy, validation success criteria, and stopping conditions.", report: "Summarize this research with cited results, decisions, verification, limitations, and a recommended configuration." };
function citationLabel(request: AssistantRequest, id: string) {
  const evidence = request.snapshot.evidence.find(item => item.id === id);
  if (!evidence) return "Evidence reference";
  const names: Record<string, string> = { validation_auprc:"validation AP", validation_auroc:"validation AUROC", train_auprc:"training AP", false_positive_count:"false positives", false_negative_count:"false negatives", threshold_best_f1:"F1 threshold" };
  const field = evidence.path.split(".").at(-1) || evidence.path;
  const label = names[field] || field.replaceAll("_", " ");
  return `${evidence.experiment_id || "Study"} · ${label}`;
}

function JsonDetail({ value, label = "Structured details" }: { value: unknown; label?: string }) {
  return <details className="mt-3"><summary className="cursor-pointer text-sm text-ink-2">{label}</summary><pre className="mt-2 overflow-auto rounded border border-line bg-paper p-3 text-xs whitespace-pre-wrap break-words">{JSON.stringify(value, null, 2)}</pre></details>;
}
function DraftReview({ value }: { value: Record<string, unknown> }) {
  return <dl className="mt-3 space-y-3">{Object.entries(value).map(([key, content]) => <div key={key}><dt className="text-xs font-medium uppercase tracking-wide text-ink-2">{key.replaceAll("_", " ")}</dt><dd className="mt-1 text-sm leading-6">{Array.isArray(content) ? <ul className="list-disc pl-5">{content.map((item, index) => <li key={index}>{typeof item === "object" && item ? <DraftReview value={item as Record<string, unknown>} /> : String(item)}</li>)}</ul> : content && typeof content === "object" ? <DraftReview value={content as Record<string, unknown>} /> : String(content ?? "Not specified")}</dd></div>)}</dl>;
}

export default function AssistantWorkspace(props: AssistantWorkspaceProps) {
  const scope = `${props.sessionId || ""}:${props.projectId || ""}:${props.replay ? "replay" : "live"}`;
  return <ScopedWorkspace key={scope} {...props} />;
}

function ScopedWorkspace({ sessionId, projectId, experimentIds = [], initialKind = "ask", group, replay = false }: AssistantWorkspaceProps) {
  const [kind, setKind] = useState<AssistantKind>(initialKind);
  const [question, setQuestion] = useState(prompts[initialKind]);
  const [capability, setCapability] = useState<Capabilities | null>(null);
  const [requests, setRequests] = useState<AssistantRequest[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [started, setStarted] = useState<string | null>(null);
  const [excludedFindingIds, setExcludedFindingIds] = useState<string[]>([]);
  const submission = useRef<{ signature: string; key: string } | null>(null);
  const actionKeys = useRef(new Map<string, string>());
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (replay) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try {
        const [caps, history] = await Promise.all([assistantApi<Capabilities>("/capabilities"), assistantApi<{ items: AssistantRequest[] }>(`/requests?${scopeQuery(sessionId, projectId)}`)]);
        if (active) { setCapability(caps); setRequests(history.items); setLoadError(""); }
      } catch (e) { if (active) setLoadError(errorText(e)); }
      finally { if (active) timer = setTimeout(refresh, 5000); }
    }
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [sessionId, projectId, replay, revision]);

  const selected = requests.find(r => r.id === selectedId) || requests[0];
  function chooseKind(value: AssistantKind) { setKind(value); setQuestion(prompts[value]); setDraft(null); setStarted(null); }
  async function perform(work: () => Promise<void>) {
    if (busy || replay) return;
    setBusy(true); setError("");
    try { await work(); if (mounted.current) setRevision(v => v + 1); }
    catch (e) { if (mounted.current) setError(errorText(e)); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function submit() {
    if (!capability?.verified || !question.trim()) return;
    const body = { kind, session_id: sessionId, project_id: projectId, experiment_ids: experimentIds, question: question.trim(), excluded_finding_ids: excludedFindingIds, ...(group ? { group } : {}) };
    const signature = JSON.stringify(body);
    if (submission.current?.signature !== signature) submission.current = { signature, key: submissionKey() };
    await perform(async () => {
      const request = await assistantApi<AssistantRequest>("/requests", { ...body, idempotency_key: submission.current!.key });
      if (!mounted.current) return;
      setRequests(rows => [request, ...rows.filter(r => r.id !== request.id)]); setSelectedId(request.id); setDraft(null);
      submission.current = null;
    });
  }
  async function requestAction(action: "cancel" | "retry" | "draft") {
    if (!selected) return;
    await perform(async () => {
      const result = await assistantApi<Record<string, unknown>>(`/requests/${encodeURIComponent(selected.id)}/${action}`, {});
      if (action === "draft" && mounted.current) setDraft(result);
    });
  }
  async function startDraft() {
    if (!draft?.id || !draft.version_hash) return;
    await perform(async () => {
      const id = String(draft.id);
      if (!actionKeys.current.has(id)) actionKeys.current.set(id, submissionKey());
      const result = await assistantApi<{ session_id: string }>(`/drafts/${encodeURIComponent(id)}/start`, { version_hash: draft.version_hash, idempotency_key: actionKeys.current.get(id) });
      if (mounted.current) setStarted(result.session_id);
    });
  }

  if (replay) return <section className="surface p-5"><h2 className="section-title">ARIA workspace</h2><p className="mt-2 text-sm text-ink-2">Recorded playback does not submit questions, create drafts, train, or publish. Open the saved session to use the assistant.</p></section>;
  return <section className="space-y-5" aria-label="ARIA research assistant">
    <header><h2 className="section-title">Work with ARIA</h2><p className="mt-1 text-sm text-ink-2">Ask questions, review proposals, and carry findings into the next study.</p></header>
    <div className="flex flex-wrap gap-2" aria-label="Assistant workflow">{(Object.keys(labels) as AssistantKind[]).map(value => <button key={value} className={`btn ${kind === value ? "btn-primary" : ""}`} aria-pressed={kind === value} onClick={() => chooseKind(value)}>{labels[value]}</button>)}</div>
    {(error || loadError) && <div role="alert" className="notice">{error || loadError}</div>}
    {!capability?.verified && <div role="status" className="notice">{capability ? capability.reason : "Checking the ARIA connection…"} Saved answers remain available. New requests require a verified ARIA channel.</div>}
    <div className="surface p-5">
      <div className="mb-3 text-xs text-ink-2">{sessionId ? `Session ${sessionId}` : projectId ? `Project ${projectId}` : "No research scope selected"}{experimentIds.length > 0 && ` · ${experimentIds.length} selected experiments`}{group && ` · ${group.dimension}: ${group.group}`}</div>
      {experimentIds.length > 0 && <p className="mb-3 break-words font-mono text-xs">{experimentIds.join(" · ")}</p>}
      <label className="block text-sm font-medium" htmlFor="aria-question">{labels[kind]}</label>
      <textarea id="aria-question" className="form-control mt-2 min-h-28 w-full" value={question} onChange={e => setQuestion(e.target.value)} maxLength={8000} />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-ink-2">Submitting a request does not start training or publish a report.</p><button className="btn btn-primary" disabled={busy || !capability?.verified || !question.trim() || (!sessionId && !projectId)} onClick={() => void submit()}>{busy ? "Working…" : "Send to ARIA"}</button></div>
    </div>
    <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="surface p-4"><h3 className="section-title">Request history</h3>{requests.length === 0 && <p className="mt-3 text-sm text-ink-2">No requests in this scope yet.</p>}<ul className="mt-3 space-y-2">{requests.map(request => <li key={request.id}><button className={`w-full rounded border p-3 text-left ${selected?.id === request.id ? "border-emerald-700 bg-emerald-50" : "border-line"}`} aria-pressed={selected?.id === request.id} onClick={() => { setSelectedId(request.id); setDraft(null); setStarted(null); }}><span className="block text-sm font-medium">{labels[request.kind] || request.kind}</span><span className="mt-1 block line-clamp-2 text-xs text-ink-2">{request.question}</span><span className="mt-2 block text-xs">{request.status.replaceAll("_", " ")}</span></button></li>)}</ul></aside>
      <article className="surface min-w-0 p-5" aria-live="polite">{!selected ? <p className="text-sm text-ink-2">Answers will appear here with the evidence available when the question was submitted.</p> : <>
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="section-title">{labels[selected.kind]}</h3><span className="status-badge">{selected.status.replaceAll("_", " ")}</span></div>
        <p className="mt-3 text-sm">{selected.question}</p>
        {selected.response && <p className="mt-2 text-xs text-ink-2">{selected.provenance?.aria_verified ? "Verified ARIA response" : "Imported response · ARIA origin is unverified; review only"}</p>}
        {selected.error != null && <p className="notice mt-3">{errorText(selected.error)}</p>}
        {selected.error_detail != null && <p className="mt-2 text-sm text-ink-2">{errorText(selected.error_detail)}</p>}
        {selected.error === "response_invalid" && <p className="mt-2 text-sm text-ink-2">This response failed validation. Submit a fresh question to request a new answer.</p>}
        {selected.error === "dispatch_ambiguous" && <p className="mt-2 text-sm text-ink-2">Dispatch could not be confirmed. An operator must inspect and reconcile the request before another attempt.</p>}
        {pendingRequest(selected.status) && <div className="mt-3 flex items-center gap-3"><p className="text-sm text-ink-2">Waiting for ARIA. You can leave and return to this request.</p><button className="btn" disabled={busy} onClick={() => void requestAction("cancel")}>Cancel request</button></div>}
        {["failed", "timed_out"].includes(selected.status) && !["response_invalid", "dispatch_ambiguous"].includes(String(selected.error)) && <button className="btn mt-3" disabled={busy || !capability?.verified} onClick={() => void requestAction("retry")}>Retry request</button>}
        {selected.response && <div className="mt-5 space-y-4">{selected.response.claims.map((claim, index) => <div key={index}><p className="text-sm leading-6">{claim.text}</p><div className="mt-1 flex flex-wrap gap-2">{claim.citations.map(id => <a key={id} className="text-xs text-emerald-800 underline" title={`${id} · ${selected.snapshot.evidence.find(item => item.id === id)?.path || ""}`} href={`#evidence-${selected.id}-${id}`} onClick={() => { const target = document.getElementById(`evidence-${selected.id}-${id}`); const container = target?.closest("details"); if (container) container.open = true; target?.querySelectorAll("details").forEach(detail => { detail.open = true; }); }}>{citationLabel(selected, id)}</a>)}</div></div>)}
          {selected.response.assumptions.length > 0 && <div><h4 className="text-sm font-medium">Assumptions</h4><ul className="mt-1 list-disc pl-5 text-sm text-ink-2">{selected.response.assumptions.map((s, i) => <li key={i}>{s}</li>)}</ul></div>}
          {selected.response.missing_evidence.length > 0 && <div><h4 className="text-sm font-medium">Missing evidence</h4><ul className="mt-1 list-disc pl-5 text-sm text-ink-2">{selected.response.missing_evidence.map((s, i) => <li key={i}>{s}</li>)}</ul></div>}
          {selected.response.draft && <><DraftReview value={selected.response.draft} />{["study_plan", "error_proposal"].includes(selected.kind) && <button className="btn" disabled={busy || !selected.provenance?.aria_verified} onClick={() => void requestAction("draft")}>Prepare draft for review</button>}</>}
        </div>}
        {draft && <div className="mt-5 border-t border-line pt-4"><h4 className="text-sm font-medium">Execution review</h4><p className="mt-2 text-sm">{String(draft.experiment_budget ?? "Not specified")} proposed experiments + 1 fixed baseline{typeof draft.experiment_budget === "number" && ` · ${draft.experiment_budget + 1} total training runs`}</p>{draft.content != null && typeof draft.content === "object" && <DraftReview value={draft.content as Record<string, unknown>} />}<p className="mt-3 text-sm text-ink-2">Starting creates a separate local research session and consumes compute under the reviewed budget.</p><button className="btn btn-primary mt-3" disabled={busy || !draft.version_hash || Boolean(started)} onClick={() => void startDraft()}>Start reviewed study</button>{started && <a className="ml-3 text-sm underline" href={`/?session=${encodeURIComponent(started)}`}>Open started study</a>}</div>}
        {selected.snapshot?.evidence && <details className="mt-5 border-t border-line pt-4"><summary className="cursor-pointer text-sm font-medium">Evidence snapshot · {selected.snapshot.evidence.length} records</summary><p className="mt-2 break-all font-mono text-xs text-ink-2">{selected.snapshot.hash}</p><ul className="mt-3 space-y-3">{selected.snapshot.evidence.map(item => <li id={`evidence-${selected.id}-${item.id}`} key={item.id} className="rounded border border-line p-3"><p className="break-words text-xs font-medium">{item.id} · {item.experiment_id} · {item.path}</p><JsonDetail value={item.value} label="Evidence value" /></li>)}</ul></details>}
      </>}</article>
    </div>
    <AssistantTools sessionId={sessionId} experimentIds={experimentIds} excludedFindingIds={excludedFindingIds} onExcludedFindingIdsChange={setExcludedFindingIds} reportRequestId={selected?.kind === "report" && selected.status === "succeeded" && selected.provenance?.aria_verified ? selected.id : undefined} />
  </section>;
}
