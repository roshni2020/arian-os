"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { benchmarkApi, type Benchmark } from "@/lib/benchmarks";
import { reviewFields, reviewOverrides, reviewValues, selectedReviewBenchmark, type ReviewValues } from "@/lib/benchmark-review";
import BenchmarkShell, { ExternalLink, Notice } from "./BenchmarkShell";
import { ReadinessPanel } from "./BenchmarkDetails";

const fieldLabels: Record<keyof ReviewValues, string> = {
  dataset_provider: "Dataset provider", dataset_identifier: "Dataset identifier", dataset_url: "Dataset URL",
  dataset_revision: "Dataset revision", repository_url: "Repository URL", task_type: "Task type",
  metric_name: "Metric", metric_direction: "Metric direction", published_score: "Published target", published_model: "Reported model",
  train_split: "Training split", validation_split: "Validation split", test_split: "Test split",
  evaluation_protocol: "Evaluation protocol", leakage_notes: "Leakage notes",
};

export default function ReviewImport({ id }: { id: string }) {
  const router = useRouter();
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [values, setValues] = useState<ReviewValues | null>(null);
  const [name, setName] = useState("");
  const [budget, setBudget] = useState("15");
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const request = useRef<{ fingerprint: string; key: string } | null>(null);
  useEffect(() => { let active = true; benchmarkApi.get(id).then(b => { if (active) { setBenchmark(b); setValues(reviewValues(b)); setName(`${b.title || "Imported benchmark"} research`); setError(""); } }).catch(e => { if (active) setError(String(e)); }); return () => { active = false; }; }, [id, retry]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!benchmark || !values || busy) return;
    setError("");
    try {
      if (!name.trim()) throw new Error("Enter a project name.");
      const count = Number(budget);
      if (!Number.isInteger(count) || count < 1 || count > 50) throw new Error("Experiment budget must be an integer from 1 to 50.");
      if (benchmark.results.length > 1 && !selected) throw new Error("Select the reported result to use as your target.");
      const overrides = reviewOverrides(selectedReviewBenchmark(benchmark, selected), values);
      const body = { benchmark_id: id, name: name.trim(), experiment_budget: count, overrides, ...(selected ? { selected_result_id: selected } : {}) };
      const fingerprint = JSON.stringify(body);
      if (request.current?.fingerprint !== fingerprint) request.current = { fingerprint, key: crypto.randomUUID() };
      setBusy(true);
      const project = await benchmarkApi.createProject({ ...body, idempotency_key: request.current!.key });
      router.push(`/projects/${encodeURIComponent(project.id)}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); setBusy(false); }
  }

  const reviewed = benchmark ? selectedReviewBenchmark(benchmark, selected) : null;
  const original = reviewed ? reviewValues(reviewed) : null;
  const changedCount = values && original ? reviewFields.filter(field => values[field] !== original[field]).length : 0;

  function renderField(field: keyof ReviewValues) {
    if (!values || !original || !reviewed) return null;
    const currentValues = values;
    const changed = values[field] !== original[field];
    const provenance = reviewed.provenance[field];
    const multiline = field === "evaluation_protocol" || field === "leakage_notes";
    return <label key={field} className={`flex min-w-0 flex-col gap-2 text-sm ${multiline ? "md:col-span-2" : ""}`}>
      <span className="font-medium">{fieldLabels[field]}</span>
      {multiline ? <textarea rows={field === "evaluation_protocol" ? 8 : 3} value={values[field]} onChange={e => setValues({ ...currentValues, [field]: e.target.value })} className={`form-control w-full resize-y ${field === "evaluation_protocol" ? "mono text-xs" : ""}`} spellCheck={false} /> : <input value={values[field]} onChange={e => setValues({ ...currentValues, [field]: e.target.value })} className="form-control w-full" placeholder="Not identified" inputMode={field === "published_score" ? "decimal" : undefined} />}
      <span className="text-xs leading-5 text-ink-2">{changed ? "User correction · not source verified" : <ExternalLink url={provenance?.source_url}>{provenance?.status === "verified" ? "Source verified" : provenance?.status === "inferred" ? "Inferred · review required" : provenance?.status === "user_edited" ? "User correction · not source verified" : "Missing source evidence"}{provenance?.source_provider ? ` · ${provenance.source_provider}` : ""}</ExternalLink>}</span>
    </label>;
  }

  return <BenchmarkShell>
    <div className="mx-auto max-w-5xl">
      <Link className="back-link" href={`/benchmarks/${encodeURIComponent(id)}`}>← Benchmark details</Link>
      <div className="mt-6">
        <h1 className="page-heading">Create a research project</h1>
        <p className="page-subtitle mt-2">Review the benchmark, choose a target and save your project specification.</p>
      </div>

      {error && <Notice error>{error}{!benchmark && <button className="ml-3 underline" onClick={() => setRetry(x => x + 1)}>Try again</button>}</Notice>}
      {!benchmark || !values ? !error && <Notice>Loading imported details…</Notice> : <>
        <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"><span className="text-ink-2">Source benchmark</span><Link className="link font-medium" href={`/benchmarks/${encodeURIComponent(id)}`}>{benchmark.title}</Link></div>
        <ReadinessPanel benchmark={benchmark} />

        <form onSubmit={create} className="space-y-5">
          <section className="surface overflow-hidden">
            <div className="border-b border-rule px-5 py-4"><h2 className="section-title">Project setup</h2></div>
            <div className="grid gap-5 p-5 md:grid-cols-[minmax(0,1fr)_200px]">
              <label className="flex flex-col gap-2 text-sm"><span className="font-medium">Project name</span><input required maxLength={200} value={name} onChange={e => setName(e.target.value)} className="form-control w-full" /><span className="text-xs text-ink-2">You can find this project in your workspace.</span></label>
              <label className="flex flex-col gap-2 text-sm"><span className="font-medium">Experiment budget</span><input type="number" required min={1} max={50} step={1} value={budget} onChange={e => setBudget(e.target.value)} className="form-control w-full" /><span className="text-xs text-ink-2">1–50 experiments</span></label>
            </div>
          </section>

          {benchmark.results.length > 0 && <fieldset className="surface min-w-0 p-5">
            <legend className="px-1 text-sm font-semibold">Reported results{benchmark.results.length > 1 ? " · choose a target" : ""}</legend>
            <p className="mb-4 text-sm leading-6 text-ink-2">Choose a result that matches your intended dataset and split. Validation scores are not test benchmark claims.</p>
            <div className="grid gap-3 md:grid-cols-2">{benchmark.results.map(result => <div key={result.id} className={`min-w-0 rounded-lg border p-4 transition-colors ${selected === result.id ? "border-teal bg-teal/5" : "border-rule"}`}>
              <label className="flex cursor-pointer items-start gap-3 text-sm">
                <input type="radio" name="selected_result" value={result.id} checked={selected === result.id} required={benchmark.results.length > 1} onChange={() => { setSelected(result.id); const chosen = reviewValues(selectedReviewBenchmark(benchmark, result.id)); setValues({ ...values, published_score: chosen.published_score, published_model: chosen.published_model, metric_name: chosen.metric_name, metric_direction: chosen.metric_direction }); }} className="mt-1 accent-teal" />
                <span className="min-w-0 flex-1 break-words"><span className="block font-medium">{result.model || "Model unknown"}</span><span className="mt-2 block text-xl font-medium tabular-nums">{result.score ?? "Score missing"}<span className="ml-2 text-xs font-normal text-ink-2">{result.metric_name || "Metric missing"}</span></span><span className="mt-1 block text-xs leading-5 text-ink-2">{result.split || "Split not identified"}</span></span>
              </label>
              <details className="mt-3 border-t border-rule pt-3 text-xs"><summary className="cursor-pointer text-ink-2">Dataset & result evidence</summary><dl className="mt-3 space-y-3">{([["Metric definition", result.metric_definition], ["Direction", result.metric_direction], ["Dataset", result.dataset_identifier], ["Revision", result.dataset_revision], ["Split", result.split]] as const).map(([label, value]) => <div key={label}><dt className="text-ink-2">{label}</dt><dd className="mt-1 break-words">{value || "Not identified"}</dd></div>)}</dl><p className="mt-3"><ExternalLink url={result.source_url}>Source evidence</ExternalLink></p></details>
            </div>)}</div>
          </fieldset>}

          <section className="surface overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-5 py-4"><h2 className="section-title">Target & metric</h2>{changedCount > 0 && <span className="status-badge">{changedCount} {changedCount === 1 ? "correction" : "corrections"}</span>}</div>
            <div className="p-5"><p className="mb-5 text-sm leading-6 text-ink-2">{benchmark.results.length ? "Values come from the source or your selected result. Corrections are recorded separately from source verification." : "No structured result was identified. Enter a target if you have one; missing fields can remain empty."}</p><div className="grid gap-5 md:grid-cols-2">{(["published_score", "metric_name", "published_model", "metric_direction"] as const).map(renderField)}</div></div>
          </section>

          <details className="surface">
            <summary className="cursor-pointer px-5 py-4 text-sm font-medium">Dataset & repository <span className="mt-1 block font-normal text-ink-2 sm:mt-0 sm:ml-2 sm:inline">Review or correct source metadata</span></summary>
            <div className="grid gap-5 border-t border-rule p-5 md:grid-cols-2">{(["dataset_provider", "dataset_identifier", "dataset_url", "dataset_revision", "repository_url", "task_type"] as const).map(renderField)}</div>
          </details>

          <details className="surface">
            <summary className="cursor-pointer px-5 py-4 text-sm font-medium">Evaluation setup <span className="mt-1 block font-normal text-ink-2 sm:mt-0 sm:ml-2 sm:inline">Splits, protocol & leakage notes</span></summary>
            <div className="border-t border-rule p-5"><p className="mb-5 text-sm leading-6 text-ink-2">Changing the execution protocol can make this project incompatible with the current executor. Metadata and compatibility are checked again when the specification is saved.</p><div className="grid gap-5 md:grid-cols-2">{(["train_split", "validation_split", "test_split", "evaluation_protocol", "leakage_notes"] as const).map(renderField)}</div></div>
          </details>

          <div className="flex flex-wrap items-center justify-between gap-4 border-t border-rule py-5">
            <p className="max-w-md text-xs leading-5 text-ink-2">Creating a project saves this specification. Research starts only when you choose Start Research.</p>
            <div className="flex flex-wrap items-center gap-3"><Link href={`/benchmarks/${encodeURIComponent(id)}`} className="btn">Cancel</Link><button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Saving project…" : "Create project"}</button></div>
          </div>
        </form>
      </>}
    </div>
  </BenchmarkShell>;
}
