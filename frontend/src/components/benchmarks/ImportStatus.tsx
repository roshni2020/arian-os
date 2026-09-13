"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { benchmarkApi, type ImportRecord } from "@/lib/benchmarks";
import BenchmarkShell, { Notice } from "./BenchmarkShell";

export default function ImportStatus({ id }: { id: string }) {
  const [record, setRecord] = useState<ImportRecord | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    benchmarkApi.getImport(id).then(value => { if (active) { setRecord(value); setError(""); } }).catch(e => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, [id, attempt]);

  return <BenchmarkShell>
    <Link href="/benchmarks" className="back-link">← Benchmarks</Link>
    <div className="mt-6 max-w-3xl">
      <h1 className="page-heading">Import status</h1>
      <p className="page-subtitle">The saved outcome of your source inspection.</p>
      {error && <Notice error>{error} <button className="underline" onClick={() => setAttempt(x => x + 1)}>Try again</button></Notice>}
      {!record && !error && <Notice>Loading saved import…</Notice>}
      {record && <section className="surface mt-7 overflow-hidden">
        <div className="p-5 sm:p-7">
          <span className={`status-badge ${record.status === "complete" ? "success" : "warning"}`}>{record.status === "complete" ? "Metadata imported" : record.status === "partial" ? "Partial import" : "Import failed"}</span>
          <h2 className="mt-4 text-xl font-medium">{record.benchmark?.title || "Source import"}</h2>
          <p className="mt-2 text-sm leading-6 text-ink-2">{record.status === "failed" ? "The source could not be imported. Review the details below before trying again." : record.status === "partial" ? "Available metadata was saved. Review the missing information before creating a project." : "Source metadata is ready to review. Check the evidence and evaluation details before creating a project."}</p>
          {record.warnings.length > 0 && <div className="mt-6 rounded-lg border border-rule bg-paper-2 p-4">
            <h3 className="text-sm font-medium">Import details</h3>
            <ul className="mt-3 space-y-2 text-sm leading-6 text-ink-2">{record.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
          </div>}
          {record.benchmark && <dl className="mt-6 grid gap-5 sm:grid-cols-2">
            <div><dt className="text-xs text-ink-2">Metadata completeness</dt><dd className="mt-1.5 text-sm font-medium">{record.benchmark.readiness.score} of {record.benchmark.readiness.total} fields</dd></div>
            <div><dt className="text-xs text-ink-2">Research execution</dt><dd className="mt-1.5 text-sm font-medium">{record.benchmark.compatibility.executable ? "Supported executor" : "Unavailable · specification can be saved"}</dd></div>
          </dl>}
        </div>
        <div className="flex flex-wrap gap-3 border-t border-rule bg-paper-2 px-5 py-4 sm:px-7">
          {record.benchmark ? <>
            <Link className="btn btn-primary" href={`/benchmarks/${encodeURIComponent(record.benchmark.id)}/review`}>Continue review</Link>
            <Link className="btn" href={`/benchmarks/${encodeURIComponent(record.benchmark.id)}`}>Inspect evidence</Link>
          </> : <Link className="btn btn-primary" href="/benchmarks/import">Import another source</Link>}
        </div>
      </section>}
    </div>
  </BenchmarkShell>;
}
