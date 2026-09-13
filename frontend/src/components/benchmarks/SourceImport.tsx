"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { benchmarkApi, type ImportRecord } from "@/lib/benchmarks";
import BenchmarkShell, { Notice } from "./BenchmarkShell";

const sources = [
  { id: "huggingface", name: "Hugging Face", detail: "Dataset", label: "Hugging Face dataset URL", placeholder: "https://huggingface.co/datasets/organization/dataset" },
  { id: "openml", name: "OpenML", detail: "Task or dataset", label: "OpenML task or dataset URL", placeholder: "https://www.openml.org/t/31" },
  { id: "github", name: "GitHub", detail: "Repository", label: "GitHub repository URL", placeholder: "https://github.com/organization/repository" },
  { id: "paper", name: "Research paper", detail: "Paper URL or DOI", label: "Paper URL or DOI", placeholder: "https://arxiv.org/abs/identifier" },
] as const;

export default function SourceImport() {
  const [url, setUrl] = useState("");
  const [source, setSource] = useState<string>("huggingface");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [record, setRecord] = useState<ImportRecord | null>(null);
  const selectedSource = sources.find(item => item.id === source)!;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(""); setRecord(null);
    try { setRecord(await benchmarkApi.importUrl(url.trim())); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return <BenchmarkShell>
    <Link href="/benchmarks" className="back-link">← Benchmarks</Link>
    <div className="mt-6 max-w-3xl">
      <h1 className="page-heading">Import a benchmark</h1>
      <p className="page-subtitle">Add a source, check its evidence, and save a research specification.</p>
    </div>

    <div className="mt-8 grid items-start gap-8 xl:grid-cols-[minmax(0,1fr)_280px]">
      <div className="min-w-0">
        <form onSubmit={submit} className="surface p-5 sm:p-7">
          <fieldset disabled={busy}>
            <legend className="section-title mb-4">Choose a source</legend>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {sources.map(item => <label key={item.id} className="relative cursor-pointer">
                <input type="radio" name="source" value={item.id} checked={source === item.id} onChange={() => { setSource(item.id); setRecord(null); }} className="peer sr-only" />
                <span className="flex h-full flex-col gap-1 rounded-lg border border-rule px-3 py-4 transition-colors peer-checked:border-[#147d70] peer-checked:bg-[#f0f8f6] peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-[#147d70] peer-disabled:cursor-wait">
                  <span className="text-sm font-medium text-ink">{item.name}</span>
                  <span className="text-xs text-ink-2">{item.detail}</span>
                </span>
              </label>)}
            </div>
          </fieldset>

          <label className="mt-7 flex flex-col gap-2 text-sm font-medium">
            {selectedSource.label}
            <input required type={source === "paper" ? "text" : "url"} value={url} onChange={e => setUrl(e.target.value)} placeholder={selectedSource.placeholder} className="form-control w-full font-normal" />
          </label>
          <p className="mt-3 text-xs leading-5 text-ink-2">The URL determines the provider. We import supported public metadata; repository code is never executed.</p>
          <div className="mt-6 flex flex-wrap items-center gap-4 border-t border-rule pt-5">
            <button className="btn btn-primary" disabled={busy} type="submit">{busy ? "Inspecting source…" : "Inspect source"}</button>
            <span className="text-xs text-ink-2">You can review the details before creating a project.</span>
          </div>
        </form>

        {busy && <Notice>Fetching metadata and checking dataset, result, and protocol evidence. This may take a moment.</Notice>}
        {error && <Notice error>{error} Your source URL is preserved; retry when the provider is available.</Notice>}

        {record && <section className="surface mt-5 p-5 sm:p-7" aria-live="polite">
          <span className={`status-badge ${record.status === "complete" ? "success" : "warning"}`}>{record.status === "partial" ? "Needs review" : record.status === "failed" ? "Import failed" : "Metadata imported"}</span>
          <h2 className="mt-3 text-lg font-medium">{record.benchmark?.title || "Source inspection complete"}</h2>
          {record.warnings.length > 0 && <ul className="mt-4 space-y-2 text-sm leading-6 text-ink-2">{record.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
          {record.benchmark && <>
            <div className="my-5 flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <p><span className="text-ink-2">Metadata</span> <span className="ml-2 font-medium">{record.benchmark.readiness.score}/{record.benchmark.readiness.total}</span></p>
              <p className="text-ink-2">{record.benchmark.compatibility.executable ? "Supported executor" : "Execution unavailable · specification can be saved"}</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link className="btn btn-primary" href={`/benchmarks/${encodeURIComponent(record.benchmark.id)}/review`}>Review imported details</Link>
              <Link className="btn" href={`/benchmarks/${encodeURIComponent(record.benchmark.id)}`}>Inspect evidence</Link>
            </div>
          </>}
          <p className="mt-5 text-xs"><Link className="link" href={`/benchmarks/imports/${encodeURIComponent(record.id)}`}>View saved import status →</Link></p>
        </section>}
      </div>

      <aside className="px-1 py-2">
        <h2 className="section-title">What happens next</h2>
        <ol className="mt-5 space-y-6 text-sm">
          {[
            ["Inspect the source", "Available dataset, result, and evaluation details are added with their sources."],
            ["Review the evidence", "Missing fields and unconfirmed access stay visible. Corrections are marked as your edits."],
            ["Save a specification", "Create a project when you’re ready. Research can run only with a supported executor."],
          ].map(([title, detail], index) => <li key={title} className="flex gap-3">
            <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-rule text-[11px] text-ink-2">{index + 1}</span>
            <div><p className="font-medium">{title}</p><p className="mt-1.5 text-xs leading-5 text-ink-2">{detail}</p></div>
          </li>)}
        </ol>
      </aside>
    </div>
  </BenchmarkShell>;
}
