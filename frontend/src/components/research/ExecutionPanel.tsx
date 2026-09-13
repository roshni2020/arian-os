"use client";

import { useEffect, useState } from "react";
import { elapsedLabel, fetchExecutionStatus, safeWandbLink, type ExecutionStatus } from "@/lib/execution-status";
import { Notice } from "../benchmarks/BenchmarkShell";

function timeLabel(value: string | null) {
  if (!value) return "Not recorded";
  const time = new Date(value);
  return Number.isFinite(time.getTime()) ? time.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" }) : "Not recorded";
}

export default function ExecutionPanel({ sessionId, replay = false, onResume, onCancel }: { sessionId: string; replay?: boolean; onResume: () => Promise<unknown>; onCancel: () => Promise<unknown> }) {
  const [status, setStatus] = useState<ExecutionStatus | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (replay) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await fetchExecutionStatus(sessionId);
        if (active) { setStatus(next); setError(""); }
      } catch (e) { if (active) setError(e instanceof Error ? e.message : String(e)); }
      finally { if (active) timer = setTimeout(refresh, 10000); }
    }
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [sessionId, replay, revision]);

  async function action(kind: "resume" | "cancel") {
    if (busy || !status || error) return;
    if (kind === "resume" && !status.recovery.resume_available || kind === "cancel" && !status.recovery.cancel_available) return;
    setBusy(true);
    try { await (kind === "resume" ? onResume() : onCancel()); setRevision(r => r + 1); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  if (replay) return <section className="surface p-6"><h2 className="section-title">Recorded playback</h2><p className="mt-2 text-sm text-ink-2">Replay reads stored experiments. Live workers, queue status and recovery controls are unavailable during playback.</p></section>;
  const current = status?.session_id === sessionId ? status : null;
  const age = current?.activity.age_seconds;
  const duration = current?.started_at ? (new Date(current.terminal ? current.last_updated_at || current.started_at : current.observed_at).getTime() - new Date(current.started_at).getTime()) / 1000 : null;
  const workerText = current?.local_worker.alive === true ? "Worker observed in this API" : current?.local_worker.alive === false ? "Registered worker has stopped" : "External worker status is unknown";

  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="section-title">Execution status</h2><p className="mt-1 text-xs text-ink-2">Recorded activity and worker observations for this session.</p></div><button className="btn" onClick={() => setRevision(r => r + 1)} disabled={busy}>Refresh status</button></div>
    {error && <Notice error>{error}{current && " Showing the last successful status; recovery controls are disabled until it refreshes."}</Notice>}
    {!current && !error && <Notice>Loading execution details…</Notice>}
    {current && <>
      <section className="surface p-5 sm:p-6">
        <div className="flex flex-wrap justify-between gap-4"><div><p className="text-xs text-ink-2">Current stage</p><h3 className="mt-1 text-xl font-semibold">{current.terminal ? current.status === "complete" ? "Research complete" : current.status === "cancelled" ? "Research cancelled" : "Execution error" : current.stage.replaceAll("_", " ")}</h3></div><span className={`status-badge self-start ${current.status === "complete" ? "success" : ["error", "cancelled"].includes(current.status) || current.activity.state === "stale" ? "warning" : ""}`}>{current.status.replaceAll("_", " ")}</span></div>
        <dl className="mt-6 grid gap-6 sm:grid-cols-3"><div><dt className="text-xs text-ink-2">Execution transport</dt><dd className="mt-2 text-sm font-medium">{current.transport === "wandb-launch" ? "W&B Launch" : "Local process"}</dd></div><div><dt className="text-xs text-ink-2">{current.terminal ? "Recorded duration" : "Elapsed since start"}</dt><dd className="mt-2 text-sm font-medium tabular-nums">{elapsedLabel(duration)}</dd></div><div><dt className="text-xs text-ink-2">ARIA experiment budget</dt><dd className="mt-2 text-sm font-medium">{current.budget.used} of {current.budget.max} used <span className="text-xs font-normal text-ink-2">· {current.budget.remaining} remaining</span></dd></div></dl>
        <p className="mt-4 text-xs text-ink-2">The fixed baseline is separate from the ARIA experiment budget.</p>
        <div className="mt-5 border-t border-rule pt-4"><p className="text-sm">{current.activity.detail}</p><dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2"><div><dt className="text-ink-2">Last recorded activity{age != null ? ` · ${elapsedLabel(age)} ago` : ""}</dt><dd className="mt-1">{timeLabel(current.last_activity_at)}</dd></div><div><dt className="text-ink-2">Status checked</dt><dd className="mt-1">{timeLabel(current.observed_at)}</dd></div></dl></div>
      </section>

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <section className="surface p-5"><h3 className="section-title">Worker & recovery</h3>{current.transport === "local" && <p className="mt-3 text-xs font-medium">{workerText}</p>}<p className="mt-3 text-sm leading-6 text-ink-2">{current.recovery.reason}</p>
          <p className="mt-3 text-xs leading-5 text-ink-2">{current.transport === "wandb-launch" ? current.remote.detail : "Local worker observations cover this API process only. An external CLI process is not visible here."}</p>
          {current.transport === "wandb-launch" && <dl className="mt-4 grid grid-cols-2 gap-4 text-sm"><div><dt className="text-xs text-ink-2">Queue state</dt><dd className="mt-1">{current.remote.queue_state || "Not verified"}</dd></div><div><dt className="text-xs text-ink-2">Agent heartbeat</dt><dd className="mt-1">{timeLabel(current.remote.heartbeat_at)}</dd></div></dl>}
          <div className="mt-4 flex flex-wrap gap-2">{current.recovery.resume_available && <button className="btn btn-primary" disabled={busy || !!error} onClick={() => action("resume")}>{busy ? "Working…" : "Resume research"}</button>}{current.recovery.cancel_available && <button className="btn" disabled={busy || !!error} onClick={() => action("cancel")}>{busy ? "Working…" : "Request cancellation"}</button>}</div>
          <div className="mt-4 flex flex-wrap gap-4 text-xs">{([["W&B project", current.links.project], ["Launch queue", current.links.launch], ["Weave traces", current.links.traces]] as const).map(([label, value]) => { const url = safeWandbLink(value); return url && <a key={label} className="link" href={url} target="_blank" rel="noreferrer">{label} ↗</a>; })}</div>
          {current.launch_refs && <details className="mt-5 border-t border-rule pt-4"><summary className="text-xs font-medium">Saved Launch references</summary><dl className="mt-3 space-y-3 text-xs">{Object.entries(current.launch_refs).map(([field, value]) => <div key={field}><dt className="text-ink-2">{field.replaceAll("_", " ")}</dt><dd className="mt-1 break-all">{value || "Not recorded"}</dd></div>)}</dl></details>}
        </section>
        <section className="surface p-5"><h3 className="section-title">Proposal feedback</h3><p className="mt-1 text-xs text-ink-2">Latest recorded proposal and decision checks.</p>{!current.proposal_feedback.length ? <p className="mt-5 text-sm text-ink-2">No proposal feedback has been recorded.</p> : <ul className="mt-4 max-h-80 divide-y divide-rule overflow-auto">{current.proposal_feedback.map(item => <li key={item.id} className="py-3"><div className="flex flex-wrap items-center gap-2"><span className={`status-badge ${item.accepted === true ? "success" : item.accepted === false ? "warning" : ""}`}>{item.accepted === true ? "Accepted" : item.accepted === false ? "Rejected" : "Not evaluated"}</span><span className="text-xs text-ink-2">{item.kind} · revision {item.state_revision ?? "not recorded"}</span></div>{item.feedback && <p className="mt-2 text-xs leading-5">{item.feedback.message || item.feedback.code}</p>}<p className="mt-2 text-[11px] text-ink-2">{timeLabel(item.ts)}</p>{item.artifact_ref && <details className="mt-2 text-xs"><summary>Artifact reference</summary><p className="mt-1 break-all text-ink-2">{item.artifact_ref}</p></details>}</li>)}</ul>}</section>
      </div>
      <section className="surface overflow-hidden"><div className="border-b border-rule px-5 py-4"><h3 className="section-title">Activity timeline</h3><p className="mt-1 text-xs text-ink-2">Recent recorded events, newest first.</p></div>{!current.events.length ? <p className="p-5 text-sm text-ink-2">No activity has been recorded.</p> : <ol className="divide-y divide-rule">{current.events.map(event => <li key={event.id} className="grid gap-2 px-5 py-4 sm:grid-cols-[170px_minmax(0,1fr)]"><time dateTime={event.ts} className="text-xs text-ink-2">{timeLabel(event.ts)}</time><div className="min-w-0"><p className="text-xs font-medium">{event.kind.replaceAll("_", " ")}</p><p className="mt-1 break-words text-sm leading-6 text-ink-2">{event.message}</p></div></li>)}</ol>}</section>
    </>}
  </div>;
}



