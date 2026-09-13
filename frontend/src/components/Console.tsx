"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, EventRow, Experiment, Health, HistoryRow, SessionSummary, SessionView, signed } from "@/lib/api";
import AriaPanel from "./AriaPanel";
import Journal from "./Journal";
import Margin from "./Margin";
import Trajectory from "./Trajectory";
import ExperimentDrawer from "./ExperimentDrawer";
import { parseReplay, replayView, ReplayRecord } from "@/lib/replay";
import BenchmarkShell from "./benchmarks/BenchmarkShell";
import ResearchAnalysis from "./research/ResearchAnalysis";
import ExecutionPanel from "./research/ExecutionPanel";

const workspaceTabs = [{ id: "overview", label: "Overview" }, { id: "compare", label: "Compare" }, { id: "errors", label: "Error analysis" }, { id: "execution", label: "Execution" }] as const;
type WorkspaceTab = typeof workspaceTabs[number]["id"];

function dateOf(view: SessionView | null): string {
  if (!view) return "";
  return new Date(view.session.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export default function Console() {
  const [health, setHealth] = useState<Health | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [view, setView] = useState<SessionView | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [selected, setSelected] = useState<Experiment | null>(null);
  const [budget, setBudget] = useState(15);
  const [mode, setMode] = useState("connected");
  const [error, setError] = useState<string | null>(null);
  const [replay, setReplay] = useState<{ active: boolean; step: number; playing: boolean }>({ active: false, step: 0, playing: false });
  const lastEvent = useRef(0);
  const [replayRecord, setReplayRecord] = useState<ReplayRecord | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("overview");
  const [setupOpen, setSetupOpen] = useState(false);
  const sourceRevision = useRef(0);
  const detailRevision = useRef(0);

  const selectSession = useCallback((id: string) => {
    sourceRevision.current += 1;
    detailRevision.current += 1;
    setSelected(null);
    lastEvent.current = 0;
    setEvents([]);
    setView(null);
    setReplayRecord(null);
    setReplay({ active: false, step: 0, playing: false });
    try {
      localStorage.setItem("wf.session", id);
    } catch {
      /* ignore */
    }
    setSessionId(id);
    const url = new URL(window.location.href);
    url.searchParams.set("session", id);
    window.history.replaceState(null, "", url);
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setError(String(e)));
    api.sessions().then((s) => {
      setSessions(s);
      const params = new URLSearchParams(window.location.search);
      const requestedTab = workspaceTabs.find(tab => tab.id === params.get("view"));
      if (requestedTab) setWorkspaceTab(requestedTab.id);
      setSetupOpen(params.get("custom") === "1");
      if (s.length && !sessionId) {
        let remembered: string | null = null;
        try {
          remembered = new URLSearchParams(window.location.search).get("session") || localStorage.getItem("wf.session");
        } catch {
          /* ignore */
        }
        selectSession(remembered && s.some((x) => x.id === remembered) ? remembered : s[0].id);
      }
    }).catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = useCallback(async () => {
    if (!sessionId || replayRecord) return;
    const revision = sourceRevision.current;
    try {
      const v = await api.session(sessionId);
      if (revision !== sourceRevision.current) return;
      setView(v);
      api.sessions().then(setSessions).catch(() => undefined);
      const ev = await api.events(sessionId, lastEvent.current);
      if (revision !== sourceRevision.current) return;
      if (ev.length) {
        lastEvent.current = ev[ev.length - 1].id;
        setEvents((prev) => [...prev, ...ev].slice(-200));
      }
      setError(null);
    } catch (e) {
      if (revision === sourceRevision.current) setError(String(e));
    }
  }, [sessionId, replayRecord]);

  useEffect(() => {
    const first = setTimeout(refresh, 0);
    const t = setInterval(refresh, 3000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [refresh]);

  useEffect(() => {
    if (!replay.active || !replay.playing || !view) return;
    const t = setTimeout(() => setReplay((r) => (r.step >= view.state.history.length ? { ...r, playing: false } : { ...r, step: r.step + 1 })), 1800);
    return () => clearTimeout(t);
  }, [replay, view]);

  const start = async () => {
    try {
      const v = await api.start({ budget, aria_mode: mode });
      setSessions(await api.sessions());
      selectSession(v.session.id);
    } catch (e) {
      setError(String(e));
    }
  };

  const history: HistoryRow[] = view?.state.history ?? [];
  const visible = replay.active ? history.slice(0, replay.step) : history;
  const replayingHistory = replay.active && replay.step < history.length;
  const finalEval = replayingHistory ? null : view?.session.final_evaluation ?? null;
  const live = !!view?.worker_alive && !replay.active;
  const modeLabel = replay.active ? "REPLAYING STORED RUN" : view?.mode_label ?? "";
  const frozenId = finalEval?.experiment_id ?? view?.session.final_decision?.recommended_final_experiment_id ?? null;
  const best = visible.length ? Math.max(...visible.map((h) => h.score)) : null;
  const baseline = view?.state.baseline_validation_auprc ?? null;
  const published = view?.benchmark.published_test_auprc ?? 0.533;
  const ariaCount = visible.filter((h) => h.iteration > 0).length;

  const loadReplay = (record: ReplayRecord) => {
    sourceRevision.current += 1;
    detailRevision.current += 1;
    setReplayRecord(record); setView(replayView(record)); setEvents(record.events);
    setError(null); setSelected(null); setReplay({ active: true, step: 1, playing: true });
  };
  const showDetails = (id: string) => {
    const revision = ++detailRevision.current;
    if (replayRecord) setSelected(replayRecord.experiments.find((e) => e.id === id) ?? null);
    else if (view) api.experiment(view.session.id, id).then(exp => { if (revision === detailRevision.current) setSelected(exp); }).catch(e => { if (revision === detailRevision.current) setError(String(e)); });
  };
  const chooseTab = (tab: WorkspaceTab) => {
    setWorkspaceTab(tab);
    const url = new URL(window.location.href);
    url.searchParams.set("view", tab);
    if (view && !replayRecord) url.searchParams.set("session", view.session.id);
    window.history.replaceState(null, "", url);
  };
  const analysisExperiments = view?.experiments.filter(exp => !replay.active || visible.some(row => row.experiment_id === exp.id)) ?? [];

  return (
    <BenchmarkShell>
    <div className="ui min-w-0 flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="page-heading">Research journal</h1>
          <p className="page-subtitle mt-2">WildfireIA · Initial attack failure prediction</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a href="#session-setup" onClick={() => setSetupOpen(true)} className="btn">Custom session</a>
          <Link href="/benchmarks" className="btn btn-primary">Explore benchmarks <span aria-hidden="true">↗</span></Link>
        </div>
      </header>

      <section id="session-setup" aria-labelledby="session-setup-title" className="surface min-w-0 scroll-mt-6">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-rule p-4 sm:px-5">
          <div>
            <h2 id="session-setup-title" className="section-title">Session workspace</h2>
            <p className="mt-1 text-xs leading-5 text-ink-2">Review a saved run or start a custom WildfireIA session.</p>
          </div>
          <span className={`status-badge inline-flex items-center gap-2 ${live ? "text-teal" : replay.active ? "text-rust" : "text-ink-2"}`}>
            {live && <span className="live-dot inline-block h-1.5 w-1.5 rounded-full bg-teal" />}
            {modeLabel || "No session"}
          </span>
        </div>
        <div className="flex flex-wrap items-end gap-3 p-4 sm:p-5">
          <label className="flex min-w-0 flex-1 basis-52 flex-col gap-1.5 text-xs font-medium text-ink-2">Saved session
            <select className="form-control min-w-0 w-full text-sm text-ink" value={sessionId ?? ""} onChange={(e) => selectSession(e.target.value)} aria-label="Session">
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>{s.id} · {s.status}{s.aria_mode !== "connected" ? ` · ${s.aria_mode}` : ""}</option>
              ))}
              {!sessions.length && <option value="">No sessions yet</option>}
            </select>
          </label>
          {view && <span className="pb-2 text-xs text-ink-2">Created {dateOf(view)}</span>}
          {view && history.length > 0 && (
            <button className="btn" onClick={async () => {
              if (replay.active) { sourceRevision.current += 1; setSelected(null); setView(null); setEvents([]); lastEvent.current = 0; setReplayRecord(null); setReplay({ active: false, step: 0, playing: false }); return; }
              try { const record = await api.replay(view.session.id); loadReplay(parseReplay(JSON.stringify(record))); }
              catch (e) { setError(String(e)); }
            }}>
              {replay.active ? "Exit replay" : "Replay"}
            </button>
          )}
          <label className="btn relative focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-teal">Import replay
            <input type="file" accept=".json,application/json" className="sr-only" aria-label="Import replay JSON" onChange={async (e) => {
              const file = e.target.files?.[0]; if (!file) return;
              try { loadReplay(parseReplay(await file.text())); } catch (err) { setError(String(err)); }
            }} />
          </label>
        </div>
        <details open={setupOpen} onToggle={event => setSetupOpen(event.currentTarget.open)} className="border-t border-rule p-4 sm:px-5">
          <summary className="cursor-pointer text-xs font-medium">Start a custom session</summary>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1.5 text-xs font-medium text-ink-2">Experiment budget
            <input type="number" min={1} max={50} value={budget} onChange={(e) => setBudget(Number(e.target.value))} className="form-control w-28 text-sm text-ink" aria-label="Experiment budget" />
          </label>
          <label className="flex min-w-0 flex-1 basis-44 flex-col gap-1.5 text-xs font-medium text-ink-2">Research mode
            <select className="form-control min-w-0 w-full text-sm text-ink" value={mode} onChange={(e) => setMode(e.target.value)} aria-label="ARIA mode">
              <option value="connected">ARIA · connected</option>
              <option value="fallback">Fallback · stub, not ARIA</option>
            </select>
          </label>
          <button onClick={start} disabled={!health?.canonical_ready} className="btn btn-primary">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4l14 8-14 8z" /></svg>
            Start autonomous research
          </button>
        </div>
        </details>
      </section>

      {error && <p role="alert" className="surface break-words border-rust px-4 py-3 text-sm text-rust">{error}</p>}
      {health && !health.canonical_ready && <p role="status" className="surface px-4 py-3 text-sm text-ink-2">WildfireIA data not set up. Run <code className="mono break-words">python -m wildfire_researcher.cli setup-data</code>.</p>}

      <div role="tablist" aria-label="Research workspace" className="flex gap-3 overflow-x-auto border-b border-rule sm:gap-5" onKeyDown={event => {
        const index = workspaceTabs.findIndex(tab => tab.id === workspaceTab);
        const next = event.key === "ArrowRight" ? (index + 1) % workspaceTabs.length : event.key === "ArrowLeft" ? (index + workspaceTabs.length - 1) % workspaceTabs.length : event.key === "Home" ? 0 : event.key === "End" ? workspaceTabs.length - 1 : null;
        if (next !== null) { event.preventDefault(); chooseTab(workspaceTabs[next].id); document.getElementById(`workspace-tab-${workspaceTabs[next].id}`)?.focus(); }
      }}>{workspaceTabs.map(tab => <button key={tab.id} id={`workspace-tab-${tab.id}`} role="tab" aria-selected={workspaceTab === tab.id} aria-controls={`workspace-panel-${tab.id}`} tabIndex={workspaceTab === tab.id ? 0 : -1} className={`shrink-0 border-b-2 px-1 pb-3 text-xs sm:text-sm ${workspaceTab === tab.id ? "border-teal font-medium text-teal" : "border-transparent text-ink-2 hover:text-ink"}`} onClick={() => chooseTab(tab.id)}>{tab.label}</button>)}</div>

      <div id="workspace-panel-overview" role="tabpanel" aria-labelledby="workspace-tab-overview" hidden={workspaceTab !== "overview"} className={workspaceTab === "overview" ? "space-y-6" : ""}>

      <section aria-labelledby="results-title" className="min-w-0">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 id="results-title" className="section-title">Results overview</h2>
          <span className="text-xs text-ink-2">AUPRC · higher is better</span>
        </div>
        <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 xl:grid-cols-4">
          <Big value={best == null ? "—" : `${(best * 100).toFixed(1)}%`} label="Best validation · 2019" sub={`Baseline ${baseline == null ? "not run" : `${(baseline * 100).toFixed(1)}%`}`} color="text-teal" />
          <Big value={finalEval ? `${(finalEval.mean_test_auprc * 100).toFixed(1)}%` : "—"} label="Our official test · 2020" sub={finalEval ? `${finalEval.seeds.length} seeds · ±${(finalEval.std_test_auprc * 100).toFixed(1)} pts` : "Test not run"} color="text-ink" />
          <Big value={`${(published * 100).toFixed(1)}%`} label="Published test · 2020" sub="WildfireIA · five-seed reference" color="text-ink" />
          <Big value={finalEval ? signed(finalEval.delta_vs_published) : "—"} label="Test difference" sub={finalEval ? (finalEval.benchmark_beaten ? "Benchmark beaten · backend certified" : finalEval.reported_above_reference ? "Above reference · uncertified" : "Below reference · uncertified") : "No test comparison yet"} color={finalEval ? (finalEval.delta_vs_published > 0 ? "text-teal" : "text-rust") : "text-ink-2"} />
        </div>
        <p className="mt-3 text-xs leading-5 text-ink-2">Validation results guide experiment selection. They do not establish a win against the published test reference.</p>
      </section>

      {view && history.length > 0 && (
        <section aria-labelledby="trajectory-title" className="surface min-w-0 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="trajectory-title" className="section-title">Experiment trajectory</h2>
            <span className="text-xs text-ink-2">Validation 2019 · seed 553371</span>
          </div>
          <div className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-label="Experiment trajectory chart; scroll horizontally on small screens"><div className="min-w-[680px]"><Trajectory history={history} target={published} selected={selected?.id} visibleCount={replay.active ? replay.step : undefined} finalTest={finalEval?.mean_test_auprc ?? null} onSelect={showDetails} /></div></div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink-2 mt-3">
            <span className="inline-flex items-center gap-2"><span className="inline-block w-2 h-2 rounded-full bg-teal" />New best</span>
            <span className="inline-flex items-center gap-2"><span className="inline-block w-2 h-2 rounded-full bg-ink" />Kept</span>
            <span className="inline-flex items-center gap-2"><span className="inline-block w-2 h-2 rounded-full border-2 border-rust" />Rejected</span>
            <span className="sm:ml-auto">Select a point to inspect the experiment</span>
          </div>
        </section>
      )}

      <section className="min-w-0 flex-grow">
        {view && <AriaPanel session={view.session} state={replay.active ? { ...view.state, pending_experiment: null, status: "complete", rejected_messages_at_this_revision: [] } : view.state} live={live} />}
        <div className="surface min-w-0 p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="section-title">Experiment journal <span className="ml-1 text-ink-2 font-normal">{visible.length}</span></h2>
            <span className="text-xs text-ink-2">Select an entry for ARIA&apos;s reasoning</span>
          </div>
          <p className="mb-4 text-xs leading-5 text-ink-2">{view ? (replay.active ? `Replaying ${replay.step} of ${history.length} stored entries · no retraining, no ARIA calls` : `${ariaCount} experiment${ariaCount === 1 ? "" : "s"} chosen by ARIA after one fixed baseline · every KEEP and REJECT is ARIA's`) : "Select a saved session or start a new research run to see its experiments here."}</p>
          {view && <div className="min-w-0 overflow-x-auto"><Journal history={visible} experiments={view.experiments} failed={replay.active ? [] : view.state.failed_experiments} frozenId={replayingHistory ? null : frozenId} onDetails={showDetails} /></div>}
        </div>
      </section>

      {view && (
        <section className="surface min-w-0 overflow-x-auto p-4 sm:p-5">
          <Margin view={view} finalEval={finalEval} events={events} hideLog={replayingHistory} />
        </section>
      )}

      </div>

      <div id={`workspace-panel-${workspaceTab === "errors" ? "errors" : "compare"}`} role="tabpanel" aria-labelledby={`workspace-tab-${workspaceTab === "errors" ? "errors" : "compare"}`} hidden={!["compare", "errors"].includes(workspaceTab)}>
        {view ? <ResearchAnalysis key={`${view.session.id}:${replayRecord ? "replay" : "live"}`} sessionId={view.session.id} experiments={analysisExperiments} kind={workspaceTab === "errors" ? "errors" : "compare"} enabled={["compare", "errors"].includes(workspaceTab)} replay={!!replayRecord} onInspect={showDetails} /> : <p className="surface p-6 text-sm text-ink-2">{sessionId ? "Loading session…" : "Select a saved session to inspect its results."}</p>}
      </div>

      {workspaceTab === "execution" && <div id="workspace-panel-execution" role="tabpanel" aria-labelledby="workspace-tab-execution">{view ? <ExecutionPanel key={`${view.session.id}:${replayRecord ? "replay" : "live"}`} sessionId={view.session.id} replay={!!replayRecord} onResume={async () => { await api.resume(view.session.id); await refresh(); }} onCancel={async () => { await api.cancel(view.session.id); await refresh(); }} /> : <p className="surface p-6 text-sm text-ink-2">{sessionId ? "Loading session…" : "Select a saved session to view its execution status."}</p>}</div>}

      {selected && <ExperimentDrawer exp={selected} onClose={() => { detailRevision.current += 1; setSelected(null); }} />}

      <footer className="mt-2 border-t border-rule pt-4 pb-2 flex flex-wrap justify-between gap-2 text-[11px] leading-5 text-ink-2">
        <span>Research prototype using historical public data. Not for operational wildfire response.</span>
        <span>CoreWeave × Weights &amp; Biases</span>
      </footer>
    </div>
    </BenchmarkShell>
  );
}

function Big({ value, label, sub, color }: { value: string; label: string; sub: string; color: string }) {
  return (
    <div className="surface flex min-w-0 flex-col gap-3 p-4 sm:p-5">
      <span className="text-xs font-medium leading-5 text-ink-2">{label}</span>
      <span className={`text-[30px] leading-none font-semibold tracking-tight tabular-nums ${color}`}>{value}</span>
      <span className="text-[11px] leading-5 text-ink-2">{sub}</span>
    </div>
  );
}
