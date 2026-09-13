"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { benchmarkApi, displayAccess, type Benchmark, type Provenance } from "@/lib/benchmarks";
import BenchmarkShell, { ExternalLink, Notice } from "./BenchmarkShell";

const fieldLabels: Record<string, string> = {
  dataset_public: "Dataset access", repository_public: "Repository access",
  dataset_identifier: "Dataset", dataset_revision: "Revision", sample_count: "Samples",
  published_score: "Published target", published_model: "Reported model",
  train_split: "Training", validation_split: "Validation", test_split: "Test",
};

function fieldLabel(field: string) {
  return fieldLabels[field] || field.replaceAll("_", " ").replace(/^./, letter => letter.toUpperCase());
}

function badgeLabel(value: string) {
  if (value === "ia_failure") return "Initial attack failure";
  return value.replaceAll("_", " ").replace(/^./, letter => letter.toUpperCase());
}

export function Evidence({ value, provenance }: { value: unknown; provenance?: Provenance }) {
  const present = value !== null && value !== undefined && value !== "";
  const structured = present && typeof value === "object";
  return <>
    <dd className="mt-1 break-words text-sm leading-6">
      {structured ? <pre className="mono max-h-80 overflow-auto rounded-md border border-rule bg-paper p-3 text-xs whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre> : present ? String(value) : <span className="text-ink-2">Not identified</span>}
    </dd>
    <dd className="mt-1 text-xs leading-5 text-ink-2">
      <ExternalLink url={provenance?.source_url}>
        {!present ? "Missing" : provenance?.status === "user_edited" ? "User correction · not source verified" : provenance?.status === "verified" ? "Source verified" : provenance?.status === "inferred" ? "Inferred · review required" : "Verification not recorded"}
        {present && provenance?.source_provider ? ` · ${provenance.source_provider}` : ""}
        {present && provenance?.confidence ? ` · ${provenance.confidence} confidence` : ""}
      </ExternalLink>
    </dd>
  </>;
}

export function Metadata({ benchmark: b }: { benchmark: Benchmark }) {
  const groups = [
    ["Overview", ["title", "description", "domain", "task_type", "publication_date"]],
    ["Published target", ["metric_name", "metric_direction", "published_score", "published_model"]],
    ["Dataset", ["dataset_provider", "dataset_identifier", "dataset_revision", "dataset_public", "repository_public", "sample_count", "license"]],
    ["Evaluation protocol", ["train_split", "validation_split", "test_split", "evaluation_protocol", "leakage_notes"]],
  ] as const;

  return <>
    <section className="surface overflow-hidden">
      <div className="border-b border-rule px-5 py-4"><h2 className="section-title">Dataset & evaluation</h2></div>
      <div className="grid lg:grid-cols-2">
        <div className="p-5 lg:border-r lg:border-rule">
          <p className="mb-4 text-xs font-medium text-ink-2">Dataset</p>
          <dl className="space-y-4 text-sm">
            {(["dataset_identifier", "dataset_provider", "sample_count", "license", "dataset_public", "repository_public"] as const).map(field => <div key={field} className="grid grid-cols-[110px_minmax(0,1fr)] gap-4">
              <dt className="text-ink-2">{fieldLabel(field)}</dt>
              <dd className="min-w-0 break-words">{field === "dataset_public" || field === "repository_public" ? displayAccess(b[field]) : field === "sample_count" && b[field] !== null ? b[field].toLocaleString() : b[field] ?? "Not identified"}</dd>
            </div>)}
          </dl>
        </div>
        <div className="border-t border-rule p-5 lg:border-t-0">
          <p className="mb-4 text-xs font-medium text-ink-2">Evaluation splits</p>
          <dl className="space-y-4 text-sm">
            {(["train_split", "validation_split", "test_split"] as const).map(field => <div key={field} className="grid grid-cols-[85px_minmax(0,1fr)] gap-4"><dt className="text-ink-2">{fieldLabel(field)}</dt><dd className="break-words">{b[field] || "Not identified"}</dd></div>)}
          </dl>
          <details className="mt-5 border-t border-rule pt-4">
            <summary className="cursor-pointer text-sm font-medium">Protocol, revision & leakage notes</summary>
            <dl className="mt-4 space-y-4">{(["dataset_revision", "evaluation_protocol", "leakage_notes"] as const).map(field => <div key={field}><dt className="text-xs text-ink-2">{fieldLabel(field)}</dt><Evidence value={b[field]} provenance={b.provenance[field]} /></div>)}</dl>
          </details>
        </div>
      </div>
    </section>
    <details className="surface mt-5">
      <summary className="cursor-pointer px-5 py-4 text-sm font-medium">All metadata & field evidence <span className="mt-1 block font-normal text-ink-2 sm:mt-0 sm:ml-2 sm:inline">Source verification for every field</span></summary>
      <div className="grid gap-x-8 gap-y-7 border-t border-rule p-5 lg:grid-cols-2">{groups.map(([title, fields]) => <section key={title} className="min-w-0"><h3 className="section-title mb-4">{title}</h3><dl className="space-y-4">{fields.map(field => <div key={field}><dt className="text-xs font-medium text-ink-2">{fieldLabel(field)}</dt><Evidence value={field === "dataset_public" || field === "repository_public" ? displayAccess(b[field]) : b[field]} provenance={b.provenance[field]} /></div>)}</dl></section>)}</div>
    </details>
  </>;
}

export function ReadinessPanel({ benchmark: b }: { benchmark: Benchmark }) {
  return <section aria-label="Benchmark readiness" className="surface my-6 grid md:grid-cols-2">
    <div className="p-5">
      <div className="flex items-center justify-between gap-3"><h2 className="section-title">Metadata completeness</h2><span className={`status-badge ${b.readiness.status === "complete" ? "success" : "warning"}`}>{b.readiness.score} / {b.readiness.total} fields</span></div>
      <p className="mt-2 text-sm text-ink-2">{b.readiness.status === "complete" ? "All required metadata is available." : "Some source details still need review."}</p>
      {b.readiness.missing.length > 0 && <details className="mt-3 text-sm"><summary className="cursor-pointer text-ink-2">View missing metadata</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-ink-2">{b.readiness.missing.map(field => <li key={field}>{fieldLabel(field)}</li>)}</ul></details>}
    </div>
    <div className="border-t border-rule p-5 md:border-t-0 md:border-l">
      <div className="flex items-center justify-between gap-3"><h2 className="section-title">Research execution</h2><span className={`status-badge ${b.compatibility.executable ? "success" : ""}`}>{b.compatibility.executable ? "Supported" : "Unavailable"}</span></div>
      <p className="mt-2 text-sm text-ink-2">{b.compatibility.executable ? "Compatible with the WildfireIA executor." : "You can save this specification for review."}</p>
      <details className="mt-3 text-sm"><summary className="cursor-pointer text-ink-2">Compatibility & comparability</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-ink-2">{b.compatibility.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul><p className="mt-2 text-ink-2">Comparability: {b.compatibility.comparability}</p></details>
    </div>
  </section>;
}

export default function BenchmarkDetails({ id }: { id: string }) {
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => { let active = true; benchmarkApi.get(id).then(b => { if (active) { setBenchmark(b); setError(""); } }).catch(e => { if (active) setError(String(e)); }); return () => { active = false; }; }, [id, retry]);

  return <BenchmarkShell>
    <Link href="/benchmarks" className="back-link">← Benchmarks</Link>
    {error ? <Notice error>{error} <button className="underline" onClick={() => setRetry(x => x + 1)}>Try again</button></Notice> : !benchmark ? <Notice>Loading benchmark evidence…</Notice> : <>
      <div className="mt-6 flex flex-col items-start justify-between gap-5 sm:flex-row">
        <div className="w-full min-w-0 max-w-3xl sm:flex-1">
          <div className="mb-3 flex flex-wrap gap-2">{[benchmark.domain, benchmark.task_type].filter((value): value is string => Boolean(value)).map((value, i) => <span key={`${value}-${i}`} className="status-badge">{badgeLabel(value)}</span>)}</div>
          <h1 className="page-heading break-words">{benchmark.title}</h1>
          {benchmark.description && <p className="page-subtitle mt-3 max-w-3xl leading-6">{benchmark.description}</p>}
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm">{([["Paper", benchmark.paper_url], ["Dataset", benchmark.dataset_url], ["Repository", benchmark.repository_url]] as const).filter(([, url]) => url).map(([label, url]) => <ExternalLink key={label} url={url}>{label}</ExternalLink>)}</div>
        </div>
        <Link href={`/benchmarks/${encodeURIComponent(id)}/review`} className="btn btn-primary shrink-0">Create project <span aria-hidden="true">→</span></Link>
      </div>

      <ReadinessPanel benchmark={benchmark} />

      <section className="surface mb-5 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-5 py-4"><h2 className="section-title">Reported results <span className="ml-2 text-sm font-normal text-ink-2">{benchmark.results.length}</span></h2><span className="text-xs text-ink-2">Select a target when you create a project</span></div>
        {!benchmark.results.length ? <div className="p-5 text-sm text-ink-2">No structured result was identified. You can enter a target during review.</div> : <div className="divide-y divide-rule">{benchmark.results.map(result => <article key={result.id} className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0"><h3 className="text-sm font-medium">{result.model || "Model not identified"}</h3><p className="mt-1 text-sm text-ink-2">{result.split || "Split not identified"}</p></div>
            <div className="text-right"><p className="text-xl font-medium tabular-nums">{result.score ?? "Score missing"}</p><p className="mt-1 text-xs text-ink-2">{result.metric_name || "Metric missing"}</p></div>
          </div>
          <details className="mt-3 text-sm"><summary className="cursor-pointer text-ink-2">Result evidence & protocol</summary><dl className="mt-4 grid gap-4 sm:grid-cols-2">{([["Metric definition", result.metric_definition], ["Direction", result.metric_direction], ["Dataset", result.dataset_identifier], ["Revision", result.dataset_revision], ["Split", result.split]] as const).map(([label, value]) => <div key={label}><dt className="text-xs text-ink-2">{label}</dt><dd className="mt-1 break-words">{value || "Not identified"}</dd></div>)}</dl><p className="mt-4"><ExternalLink url={result.source_url}>Result source</ExternalLink></p></details>
        </article>)}</div>}
        <p className="border-t border-rule bg-paper px-5 py-3 text-xs leading-5 text-ink-2">Scores are tied to their dataset revision, metric and evaluation split. Validation results do not establish test benchmark performance.</p>
      </section>

      <Metadata benchmark={benchmark} />

      <details className="surface mt-5">
        <summary className="cursor-pointer px-5 py-4 text-sm font-medium">Resources & synchronization history</summary>
        <div className="grid gap-6 border-t border-rule p-5 md:grid-cols-2">
          <ul className="space-y-3 text-sm">{([["Paper", benchmark.paper_url], ["Dataset", benchmark.dataset_url], ["Repository", benchmark.repository_url]] as const).map(([label, url]) => <li key={label}>{url ? <ExternalLink url={url}>{label}: {url}</ExternalLink> : <span className="text-ink-2">{label}: not identified</span>}</li>)}</ul>
          <ul className="space-y-4 text-sm text-ink-2">{benchmark.sources.map((source, i) => <li key={i}><ExternalLink url={source.external_url}>{source.provider} · {source.external_id}</ExternalLink><p className="mt-1 text-xs">Last synchronized: {source.last_synced_at || "Unknown"}</p></li>)}</ul>
        </div>
      </details>
    </>}
  </BenchmarkShell>;
}
