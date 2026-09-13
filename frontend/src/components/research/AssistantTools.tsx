"use client";
import { useEffect, useRef, useState } from "react";
import { assistantApi, errorText, seedList, submissionKey } from "@/lib/assistant";
import { publishedReportUrl } from "@/lib/report-preview";
import ReportPreview from "./ReportPreview";

type Verification = { id: string; status: string; error?:unknown; plan_hash: string; plan: { seeds: number[]; max_runs: number; baseline_id: string; candidate_id: string }; children: { id: string; arm: string; seed: number; status: string; result?: unknown; error?: unknown }[]; summary: { mean_delta?: number | null; std_delta?:number|null; min_delta?:number|null; max_delta?:number|null; expected_pairs?:number; variability_label?:string; complete_pairs?: number; limitations?: string[] } };
type Report = { id: string; markdown: string; evidence_hash: string; publication: {status: string; url?: string} | null; created_at: string };
type Finding = { id: string; session_id: string; experiment_id: string; config: {model?: string; feature_protocol?:string}; metrics: {validation_auprc?:number; false_negative_count?:number; false_positive_count?:number}; outcome?:string; limitations?:string[]; created_at?:string; verification?:{id?:string;status?:string;[key:string]:unknown}[] };
function metric(value: unknown) { return typeof value === "number" && Number.isFinite(value) ? value.toFixed(4) : "Not recorded"; }
function RunResult({result}: {result: unknown}) {
  if (!result || typeof result !== "object") return <>Pending</>;
  const value = result as Record<string,unknown>;
  return <>AP {metric(value.validation_auprc)}{typeof value.runtime_seconds === "number" && ` · ${value.runtime_seconds.toFixed(1)}s`}</>;
}

export default function AssistantTools({ sessionId, experimentIds, reportRequestId, excludedFindingIds = [], onExcludedFindingIdsChange }: { sessionId?: string; experimentIds: string[]; reportRequestId?:string; excludedFindingIds?:string[]; onExcludedFindingIdsChange?:(ids:string[])=>void }) {
  const [tab, setTab] = useState<"verification" | "findings" | "reports">("verification");
  const [seeds, setSeeds] = useState("17, 42, 103");
  const [search, setSearch] = useState("");
  const [verifications, setVerifications] = useState<Verification[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const keys = useRef(new Map<string, string>());
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    if (!sessionId) return;
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const resource = tab === "verification" ? "verifications" : tab;
        const result = await assistantApi<{ items: never[] }>(`/${resource}?session_id=${encodeURIComponent(sessionId!)}${tab === "findings" ? `&q=${encodeURIComponent(search)}` : ""}`);
        if (current) { setLoadError(""); if (tab === "verification") setVerifications(result.items); else if (tab === "reports") setReports(result.items); else setFindings(result.items); }
      } catch (e) { if (current) setLoadError(errorText(e)); }
      finally { if (current && tab === "verification") timer = setTimeout(load, 5000); }
    }
    void load(); return () => { current = false; clearTimeout(timer); };
  }, [sessionId, tab, search, revision]);
  function key(name: string) { if (!keys.current.has(name)) keys.current.set(name, submissionKey()); return keys.current.get(name)!; }
  async function action(path: string, body: unknown) {
    if (busy) return;
    setBusy(true); setError("");
    try { await assistantApi(path, body); if (path === "/reports") keys.current.delete(`report:${sessionId}:${reportRequestId || "local"}`); if (active.current) setRevision(r => r + 1); }
    catch (e) { if (active.current) setError(errorText(e)); }
    finally { if (active.current) setBusy(false); }
  }
  async function prepareVerification() {
    try {
      const parsed = seedList(seeds);
      if (parsed.length < 2) throw new Error("Choose at least two seeds to measure training variability.");
      if (parsed.length * 2 > 20) throw new Error("Choose at most 10 seeds (20 paired training runs).");
      await action("/verifications", { session_id: sessionId, baseline_id: experimentIds[0], candidate_id: experimentIds[1], seeds: parsed, max_runs: parsed.length * 2, idempotency_key: key(`verify:${experimentIds.join(":")}:${seeds}`) });
    } catch (e) { setError(errorText(e)); }
  }
  return <section className="surface p-5" aria-label="Research follow-through">
    <div className="flex flex-wrap gap-2">{(["verification", "findings", "reports"] as const).map(value => <button className={`btn ${tab === value ? "btn-primary" : ""}`} key={value} aria-pressed={tab === value} onClick={() => { setTab(value); setError(""); }}>{value === "verification" ? "Verify improvement" : value === "findings" ? "Related findings" : "Report & export"}</button>)}</div>
    {!sessionId ? <p className="mt-4 text-sm text-ink-2">These tools become available after a research session has recorded experiments.</p> : <>
      {(error || loadError) && <p role="alert" className="notice mt-3">{error || loadError}</p>}
      {tab === "verification" && <div className="mt-4 space-y-4"><p className="text-sm text-ink-2">Repeat the selected baseline and candidate on paired validation seeds. This measures training variability on the existing validation set; it does not evaluate the sealed test set.</p><p className="break-words text-xs">Baseline: {experimentIds[0] || "Select a baseline in Compare"}<br />Candidate: {experimentIds[1] || "Select a candidate in Compare"}</p><label className="block text-sm">Seeds<input className="form-control mt-1 block w-full max-w-sm" value={seeds} onChange={e => setSeeds(e.target.value)} /></label><button className="btn" disabled={busy || experimentIds.length !== 2 || experimentIds[0] === experimentIds[1]} onClick={() => void prepareVerification()}>Prepare verification plan</button>
        {verifications.length === 0 && <p className="text-sm text-ink-2">No verification studies yet. Preparing a plan does not train models.</p>}
        {verifications.map(study => <article key={study.id} className="border-t border-line pt-4"><div className="flex flex-wrap justify-between gap-2"><h4 className="text-sm font-medium">Validation verification</h4><span className="status-badge">{study.status}</span></div><p className="mt-2 break-words text-xs">{study.plan.baseline_id} → {study.plan.candidate_id}</p><p className="mt-2 text-sm">{study.plan.seeds.length} paired seeds · {study.children.length || study.plan.seeds.length * 2} planned runs</p>
          {["draft", "failed", "interrupted"].includes(study.status) && <><p className="mt-2 text-sm text-ink-2">Starting consumes compute for this frozen plan, separately from the discovery budget.</p><button className="btn btn-primary mt-2" disabled={busy} onClick={() => void action(`/verifications/${encodeURIComponent(study.id)}/start`, { plan_hash: study.plan_hash })}>{study.status === "draft" ? "Start validation verification" : "Resume validation verification"}</button></>}
          {["running", "queued"].includes(study.status) && <button className="btn mt-2" disabled={busy} onClick={() => void action(`/verifications/${encodeURIComponent(study.id)}/cancel`, {})}>Cancel verification</button>}
          {study.status === "running" && <button className="btn mt-2 ml-2" disabled={busy} onClick={() => void action(`/verifications/${encodeURIComponent(study.id)}/start`, { plan_hash: study.plan_hash })}>Resume interrupted verification</button>}
          {study.error != null && <p role="alert" className="notice mt-3">{errorText(study.error)}</p>}
          <p className="mt-3 text-sm">Completed pairs: {study.summary.complete_pairs ?? 0} / {study.summary.expected_pairs ?? study.plan.seeds.length} · Mean candidate−baseline AP: {metric(study.summary.mean_delta)}</p>
          <p className="mt-2 text-xs text-ink-2">Standard deviation: {metric(study.summary.std_delta)} · Minimum: {metric(study.summary.min_delta)} · Maximum: {metric(study.summary.max_delta)}</p>
          {study.summary.variability_label && <p className="mt-2 text-sm">{study.summary.variability_label}</p>}
          <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th className="p-2">Arm</th><th className="p-2">Seed</th><th className="p-2">Status</th><th className="p-2">Result / error</th></tr></thead><tbody>{study.children.map(child => <tr key={child.id} className="border-t border-line"><td className="p-2">{child.arm}</td><td className="p-2">{child.seed}</td><td className="p-2">{child.status}</td><td className="p-2 break-words">{child.error ? errorText(child.error) : <RunResult result={child.result} />}</td></tr>)}</tbody></table></div>
          {study.summary.limitations?.map((text, i) => <p key={i} className="mt-2 text-xs text-ink-2">{text}</p>)}
        </article>)}
      </div>}
      {tab === "findings" && <div className="mt-4 space-y-3"><p className="text-sm text-ink-2">Findings from compatible research sessions, including unsuccessful ideas. Eligibility is determined by the recorded protocol and evidence.</p><div className="flex flex-wrap gap-2"><input aria-label="Search related findings" placeholder="Search findings…" className="form-control min-w-0 flex-1" value={search} onChange={e => setSearch(e.target.value)} /><button className="btn" disabled={busy} onClick={() => void action("/findings/refresh", { session_id: sessionId })}>Refresh findings index</button></div>{findings.length === 0 && <p className="text-sm text-ink-2">No eligible findings match. Refresh the index to include recorded experiments.</p>}{findings.map((finding, i) => <article key={finding.id || i} className="border-t border-line pt-3"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-medium">{finding.config.model || "Recorded model"} · {finding.config.feature_protocol || "Recorded features"}</h4><span className="status-badge">{finding.outcome || "Unreviewed"}</span></div><p className="mt-2 text-sm">Validation AP {metric(finding.metrics.validation_auprc)} · Misses {finding.metrics.false_negative_count ?? "Unknown"} · False alarms {finding.metrics.false_positive_count ?? "Unknown"}</p><a className="mt-2 inline-block break-words text-xs text-emerald-800 underline" href={`/?session=${encodeURIComponent(finding.session_id)}&view=compare`}>{finding.session_id} / {finding.experiment_id}</a><p className="mt-2 text-xs text-ink-2">Compatible protocol · {finding.verification?.length ? "Validation verification recorded" : "Unverified discovery finding"}{finding.created_at && ` · ${new Date(finding.created_at).toLocaleDateString()}`}</p><label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={!excludedFindingIds.includes(finding.id)} disabled={!onExcludedFindingIdsChange} onChange={e => onExcludedFindingIdsChange?.(e.target.checked ? excludedFindingIds.filter(id => id !== finding.id) : [...excludedFindingIds, finding.id])} />Use in new ARIA requests</label>{finding.limitations?.map((text, index) => <p key={index} className="mt-1 text-xs text-ink-2">{text}</p>)}</article>)}</div>}
      {tab === "reports" && <div className="mt-4 space-y-4"><p className="text-sm text-ink-2">Create a local report from frozen recorded evidence. Use Research report above to request an ARIA narrative. Neither action runs final evaluation or promotes a model.</p><button className="btn" disabled={busy} onClick={() => void action("/reports", { session_id: sessionId, assistant_request_id: reportRequestId, idempotency_key: key(`report:${sessionId}:${reportRequestId || "local"}`) })}>{reportRequestId ? "Create report with selected ARIA narrative" : "Create local report"}</button>{reports.length === 0 && <p className="text-sm text-ink-2">No reports yet.</p>}{reports.map(report => <article key={report.id} className="border-t border-line pt-4"><p className="text-sm font-medium">Report · {new Date(report.created_at).toLocaleString()}</p><ReportPreview markdown={report.markdown} /><div className="mt-3 flex flex-wrap gap-2"><a className="btn" href={`/api/assistant/reports/${encodeURIComponent(report.id)}/export?format=markdown`} download>Export Markdown</a><a className="btn" href={`/api/assistant/reports/${encodeURIComponent(report.id)}/export?format=json`} download>Export JSON</a><button className="btn" disabled={busy || report.publication?.status === "published"} onClick={() => void action(`/reports/${encodeURIComponent(report.id)}/publish`, { evidence_hash: report.evidence_hash })}>{report.publication?.status === "published" ? "Published" : report.publication?.status === "pending" ? "Reconcile publication" : "Publish reviewed report to W&B"}</button></div>{report.publication != null && <p className="mt-2 break-words text-xs">{report.publication.status}{publishedReportUrl(report.publication.url) && <a className="ml-2 text-emerald-800 underline" href={publishedReportUrl(report.publication.url)!} target="_blank" rel="noreferrer">Open published report</a>}</p>}</article>)}</div>}
    </>}
  </section>;
}
