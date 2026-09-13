"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { benchmarkApi, displayAccess, displayValue, Project, safeJournalUrl } from "@/lib/benchmarks";
import Shell, { ExternalLink } from "./BenchmarkShell";
import AssistantWorkspace from "../research/AssistantWorkspace";

export function ProjectList() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    benchmarkApi.projects().then(({ items }) => { if (active) { setProjects(items); setError(""); } }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [attempt]);

  return <Shell>
    <div className="flex flex-wrap items-start justify-between gap-5">
      <div><h1 className="page-heading">Projects</h1><p className="page-subtitle">Saved research specifications and their linked sessions.</p></div>
      <div className="flex flex-wrap gap-2">
        <Link className="btn" href="/?custom=1#session-setup">Custom project</Link>
        <Link className="btn btn-primary" href="/benchmarks">New from benchmark</Link>
      </div>
    </div>
    {error ? <div role="alert" className="surface mt-8 border-rust p-5 text-sm"><p>{error}</p><button className="btn mt-3" onClick={() => setAttempt(a => a + 1)}>Retry loading projects</button></div>
      : projects === null ? <div role="status" className="surface mt-8 p-8 text-sm text-ink-2">Loading projects…</div>
      : projects.length === 0 ? <div className="surface mt-8 px-6 py-14 text-center"><h2 className="text-lg font-medium">Your first project starts with a benchmark</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-ink-2">Choose a benchmark, review its evidence, and save the specification here.</p><Link className="btn btn-primary mt-6" href="/benchmarks">Explore benchmarks</Link></div>
      : <section className="surface mt-8 overflow-hidden" aria-label="Saved projects">
        <div className="flex items-center justify-between border-b border-rule px-5 py-4"><h2 className="section-title">Saved projects <span className="ml-2 text-ink-2">{projects.length}</span></h2><p className="hidden text-xs text-ink-2 sm:block">Source snapshots are preserved</p></div>
        <div className="hidden grid-cols-[minmax(0,1fr)_150px_130px_150px_24px] gap-5 border-b border-rule bg-paper-2 px-5 py-3 text-xs text-ink-2 lg:grid" aria-hidden="true"><span>Project</span><span>Session</span><span>Metadata</span><span>Execution</span><span /></div>
        <ul className="divide-y divide-rule">{projects.map(project => <li key={project.id}>
          <Link href={`/projects/${encodeURIComponent(project.id)}`} className="group grid items-center gap-4 px-5 py-5 transition-colors hover:bg-paper-2 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#147d70] lg:grid-cols-[minmax(0,1fr)_150px_130px_150px_24px] lg:gap-5">
            <div className="min-w-0"><h3 className="break-words text-sm font-medium group-hover:text-[#147d70]">{project.name}</h3><p className="mt-1.5 truncate text-xs text-ink-2">{project.snapshot.title} <span className="mx-1">·</span> {project.experiment_budget} experiment{project.experiment_budget === 1 ? "" : "s"}</p></div>
            <div><span className={`status-badge ${project.session_id ? "success" : ""}`}>{project.session_id ? "Session linked" : "Specification saved"}</span></div>
            <p className="text-xs"><span className="mr-2 text-ink-2 lg:hidden">Metadata</span><span className="tabular-nums">{project.snapshot.readiness.score}/{project.snapshot.readiness.total}</span> <span className="text-ink-2">complete</span></p>
            <p className="text-xs"><span className="mr-2 text-ink-2 lg:hidden">Execution</span>{project.compatibility.executable ? "Supported" : "Unavailable"}</p>
            <span aria-hidden="true" className="hidden text-right text-ink-2 lg:block">→</span>
          </Link>
        </li>)}</ul>
      </section>}
  </Shell>;
}

export default function ProjectOverview({ id }: { id: string }) {
  const [planning, setPlanning] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [journal, setJournal] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    benchmarkApi.project(id).then(value => { if (active) { setProject(value); setError(""); } }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [id, attempt]);

  async function start() {
    if (!project || project.session_id || starting) return;
    setStarting(true); setError("");
    try {
      const result = await benchmarkApi.start(project.id);
      setProject(result.project);
      const destination = safeJournalUrl(result.journal_url);
      if (!destination) throw new Error("Research session linked, but its journal URL is invalid. Open the research journal from navigation.");
      setJournal(destination);
      try { localStorage.setItem("wf.session", result.session_id); } catch { /* Journal URL remains available if storage is disabled. */ }
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to start research."); }
    finally { setStarting(false); }
  }

  if (!project) return <Shell><Link href="/projects" className="back-link">← Projects</Link><div className="surface mt-6 p-6 text-sm">{error ? <div role="alert"><p>{error}</p><button className="btn mt-4" onClick={() => setAttempt(a => a + 1)}>Retry loading project</button></div> : <p role="status" className="text-ink-2">Loading project…</p>}</div></Shell>;
  const snapshot = project.snapshot;
  const selected = snapshot.results.find(result => result.id === project.selected_result_id);
  const edited = Object.entries(snapshot.provenance).filter(([, provenance]) => provenance.status === "user_edited");
  const fields: [string, unknown][] = [
    ["Dataset", snapshot.dataset_identifier], ["Dataset revision", snapshot.dataset_revision],
    ["Dataset access", displayAccess(snapshot.dataset_public)], ["Repository access", displayAccess(snapshot.repository_public)],
    ["Task", snapshot.task_type], ["Metric", snapshot.metric_name],
    ["Published reference / reviewed target", snapshot.published_score], ["Target model", snapshot.published_model],
    ["Train split", snapshot.train_split], ["Validation split", snapshot.validation_split],
    ["Test split", snapshot.test_split], ["License", snapshot.license],
  ];

  return <Shell>
    <Link href="/projects" className="back-link">← Projects</Link>
    <div className="mt-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0"><h1 className="page-heading break-words">{project.name}</h1><p className="page-subtitle">{snapshot.title}</p></div>
      <span className={`status-badge mt-1 ${project.session_id ? "success" : ""}`}>{project.session_id ? "Research session linked" : "Specification saved"}</span>
    </div>
    {error && <p role="alert" className="surface mt-5 border-rust p-4 text-sm text-rust">{error}</p>}

    <div className="mt-8 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-6">
        <section className="surface p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="section-title">Plan your research</h2><p className="mt-1 text-xs text-ink-2">Review ARIA’s proposed study, criteria and budget before starting.</p></div><button className="btn" onClick={() => setPlanning(value=>!value)}>{planning ? "Close planning" : "Plan with ARIA"}</button></div></section>
        {planning && <AssistantWorkspace projectId={project.id} sessionId={project.session_id ?? undefined} initialKind="study_plan" />}
        <section aria-labelledby="snapshot-heading" className="surface overflow-hidden">
          <div className="border-b border-rule px-5 py-5 sm:px-6"><h2 id="snapshot-heading" className="section-title">Saved benchmark specification</h2><p className="mt-2 text-xs leading-5 text-ink-2">This snapshot stays unchanged when benchmark sources are refreshed.</p></div>
          <dl className="grid gap-x-8 gap-y-5 p-5 sm:grid-cols-2 sm:p-6">{fields.map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-xs text-ink-2">{label}</dt><dd className="mt-1.5 break-words text-sm leading-6">{displayValue(value)}</dd></div>)}</dl>
          {selected && <div className="border-t border-rule bg-paper-2 p-5 text-xs leading-5 sm:px-6">
            <p className="font-medium">Selected result: {selected.id}</p>
            <p className="mt-2 text-ink-2">Metric definition: {displayValue(selected.metric_definition)}</p>
            <p className="mt-1 text-ink-2">Result split: {displayValue(selected.split)} · Direction: {displayValue(selected.metric_direction)}</p>
            <p className="mt-1 break-words text-ink-2">Result dataset revision: {displayValue(selected.dataset_revision)}</p>
          </div>}
        </section>

        <section className="surface p-5 sm:p-6" aria-labelledby="protocol-heading">
          <h2 id="protocol-heading" className="section-title">Evaluation protocol</h2>
          {snapshot.evaluation_protocol && Object.keys(snapshot.evaluation_protocol).length > 0 ? <dl className="mt-4 divide-y divide-rule">{Object.entries(snapshot.evaluation_protocol).map(([field, value]) => <div key={field} className="grid gap-1.5 py-3 text-sm sm:grid-cols-[160px_minmax(0,1fr)] sm:gap-5"><dt className="text-ink-2">{field.replaceAll("_", " ")}</dt><dd className="min-w-0 whitespace-pre-wrap break-words leading-6">{displayValue(value)}</dd></div>)}</dl> : <p className="mt-4 text-sm text-ink-2">{displayValue(snapshot.evaluation_protocol)}</p>}
          <div className="mt-4 border-t border-rule pt-4"><h3 className="text-xs font-medium">Leakage restrictions</h3><p className="mt-2 text-sm leading-6 text-ink-2">{displayValue(snapshot.leakage_notes)}</p></div>
        </section>

        {edited.length > 0 && <section className="surface p-5 sm:p-6"><h2 className="section-title">User corrections</h2><p className="mt-2 text-xs leading-5 text-ink-2">Values edited during review. These corrections are not source verification.</p><ul className="mt-4 space-y-2 text-sm">{edited.map(([field, provenance]) => <li key={field} className="break-words"><span className="text-ink-2">{field.replaceAll("_", " ")}:</span> {displayValue(provenance.value)}</li>)}</ul></section>}

        <details className="surface p-5 sm:p-6">
          <summary className="section-title cursor-pointer">Saved field provenance</summary>
          <p className="mt-3 text-xs leading-5 text-ink-2">Sources and verification statuses captured with this specification. User corrections remain unverified.</p>
          <dl className="mt-5 grid gap-5 sm:grid-cols-2">{Array.from(new Set(["dataset_identifier", "dataset_revision", "dataset_url", "repository_url", "paper_url", "task_type", "metric_name", "metric_direction", "published_score", "published_model", "train_split", "validation_split", "test_split", "evaluation_protocol", "leakage_notes", ...Object.keys(snapshot.provenance)])).map(field => {
            const provenance = snapshot.provenance[field];
            return <div key={field} className="min-w-0 border-t border-rule pt-4"><dt className="text-xs font-medium">{field.replaceAll("_", " ")}</dt><dd className="mt-2 space-y-2 break-words text-xs leading-5"><p className="whitespace-pre-wrap">{displayValue(provenance ? provenance.value : snapshot[field as keyof typeof snapshot])}</p><p className="text-ink-2">Status: {provenance?.status.replaceAll("_", " ") ?? "Not recorded"} · Confidence: {provenance?.confidence ?? "Not recorded"}</p>{provenance?.source_url ? <p><ExternalLink url={provenance.source_url}>{provenance.source_provider ?? "Saved source"}</ExternalLink></p> : <p className="text-ink-2">Source: {provenance?.source_provider ?? "Not recorded"}</p>}</dd></div>;
          })}</dl>
        </details>
        <p className="px-1 text-sm"><Link className="link" href={`/benchmarks/${encodeURIComponent(project.benchmark_id)}`}>View current benchmark and source provenance →</Link></p>
      </div>

      <section aria-labelledby="execution-heading" className="surface order-first overflow-hidden xl:order-none">
        <div className="p-5 sm:p-6">
          <h2 id="execution-heading" className="section-title">Research execution</h2>
          <p className="mt-4 text-sm font-medium">{project.compatibility.executable ? "Supported by the WildfireIA executor" : "Execution unavailable"}</p>
          {project.compatibility.reasons.length > 0 && <ul className="mt-3 space-y-2 text-xs leading-5 text-ink-2">{project.compatibility.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>}
          <dl className="mt-5 space-y-4 border-t border-rule pt-5">
            <div className="flex items-center justify-between gap-3 text-sm"><dt className="text-ink-2">Experiment budget</dt><dd className="font-medium tabular-nums">{project.experiment_budget}</dd></div>
            <div className="flex items-center justify-between gap-3 text-sm"><dt className="text-ink-2">Metadata completeness</dt><dd className="font-medium tabular-nums">{snapshot.readiness.score}/{snapshot.readiness.total}</dd></div>
          </dl>
          {snapshot.readiness.missing.length > 0 && <p className="mt-3 text-xs leading-5 text-ink-2">Missing: {snapshot.readiness.missing.map(field => field.replaceAll("_", " ")).join(", ")}</p>}
          <div className="mt-5 border-t border-rule pt-4"><p className="text-xs font-medium">Comparability</p><p className="mt-2 text-xs leading-5 text-ink-2">{project.compatibility.comparability}</p></div>
        </div>
        <div className="border-t border-rule bg-paper-2 p-5 sm:p-6">
          {project.session_id ? <Link className="btn btn-primary w-full justify-center" href={journal ?? `/?session=${encodeURIComponent(project.session_id)}`}>Open research journal →</Link> : <button className="btn btn-primary w-full justify-center" disabled={starting || !project.compatibility.executable} onClick={start}>{starting ? "Connecting research session…" : "Start Research"}</button>}
          <p className="mt-3 text-xs leading-5 text-ink-2">{project.session_id ? "This project is linked to its existing research session." : "Saving a specification does not start research."}</p>
          {project.session_id && <nav aria-label="Session analysis" className="mt-4 flex flex-wrap gap-x-4 gap-y-3 text-xs">{[{ view: "compare", label: "Compare experiments" }, { view: "errors", label: "Error analysis" }, { view: "execution", label: "Execution status" }].map(item => <Link key={item.view} className="link" href={`/?session=${encodeURIComponent(project.session_id!)}&view=${item.view}`}>{item.label} →</Link>)}</nav>}
          {project.compatibility.executable && <p className="mt-3 text-xs leading-5 text-ink-2">Start Research connects real ARIA to the research journal. Validation experiments do not establish that a published test score has been beaten.</p>}
          {starting && <p role="status" className="mt-3 text-xs leading-5">Waiting for the backend to link the session. This can take a moment.</p>}
        </div>
      </section>
    </div>
  </Shell>;
}

