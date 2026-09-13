"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { benchmarkApi, type Benchmark, type CatalogQuery } from "@/lib/benchmarks";
import BenchmarkShell, { Icon, Notice } from "./BenchmarkShell";

const PROVIDERS: Record<string, string> = { huggingface: "Hugging Face", openml: "OpenML", github: "GitHub", paper: "Paper", curated: "Curated", crossref: "Crossref", arxiv: "arXiv" };
const MISSING_LABEL: Record<string, string> = { dataset_url: "dataset access", metric_name: "metric", published_score: "published result", splits: "splits", official_split: "splits", repository_url: "code", evaluation_script: "evaluation script" };

export function cleanDescription(text: string | null): string {
  if (!text) return "";
  return text.replace(/^\s*Dataset Card for ["“]?[^\n"”]*["”]?\s*/i, "").replace(/\bDataset Summary\b\s*/i, "").replace(/\*\*[^*]+\*\*:?/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/#{1,6}\s*/g, "").replace(/\s+/g, " ").trim();
}

/** Cross-validation and an unfrozen recipe never imply an official held-out split. */
export function splitLabel(b: Pick<Benchmark, "train_split" | "test_split" | "evaluation_protocol">): string {
  const ev = (b.evaluation_protocol ?? {}) as Record<string, unknown>;
  const kind = String(ev.estimation_procedure_type ?? "").toLowerCase();
  if (kind.includes("crossvalidation") || /cross-validation/i.test(b.test_split ?? "")) return `${ev.number_folds ?? "k"}-fold cross-validation · no fixed test split`;
  if (/frozen indices unavailable/i.test(b.test_split ?? "")) return "Recipe only · no frozen split";
  if (b.train_split && b.test_split && b.train_split.length + b.test_split.length < 30) return `train ${b.train_split} · test ${b.test_split}`;
  if (b.test_split) return `test ${b.test_split.length > 32 ? b.test_split.slice(0, 31) + "…" : b.test_split}`;
  return "Not identified";
}

function sourceLabel(b: Benchmark): string {
  const names = b.sources.map(s => s.provider).filter((s, i, list) => list.indexOf(s) === i);
  return (names.length ? names : [b.source || "Source unknown"]).map(s => PROVIDERS[s] || s).join(" / ");
}

function DatasetGlyph({ benchmark: b }: { benchmark: Benchmark }) {
  const domain = (b.domain || "").toLowerCase();
  const kind = /wildfire/.test(domain) ? "wildfire" : /health|medic/.test(domain) ? "health" : /earth|satellite|geospatial|disaster/.test(domain) ? "earth" : "";
  return <span className={`benchmark-glyph ${kind}`} aria-hidden="true"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    {kind === "wildfire" ? <path d="M12 3c1 4-4 5-4 9 0 2 1 3 2 4-1-4 2-4 3-7 3 3 5 5 5 8a6 6 0 0 1-12 0C4 11 10 9 12 3Z" /> : kind === "health" ? <><rect x="4" y="4" width="16" height="16" rx="4" /><path d="M8 12h8M12 8v8" /></> : kind === "earth" ? <><circle cx="12" cy="12" r="8" /><path d="M4 12h16M12 4a17 17 0 0 1 0 16 17 17 0 0 1 0-16Z" /></> : <><path d="M5 5h14v14H5ZM5 10h14M10 5v14" /><path d="M14 14h2M14 16h2" /></>}
  </svg></span>;
}

function BenchmarkRow({ b, candidate = false, importing, onImport }: { b: Benchmark; candidate?: boolean; importing?: boolean; onImport?: () => void }) {
  const title = b.title || b.dataset_identifier || "Untitled benchmark";
  const datasetAccess = b.dataset_public === true ? "Public data" : b.dataset_public === false ? "Restricted data" : "Data access unconfirmed";
  const codeAccess = b.repository_public === true ? "Public code" : b.repository_public === false ? "Restricted code" : "Code access unconfirmed";
  const missing = b.readiness.missing.map(m => MISSING_LABEL[m] || m.replaceAll("_", " "));
  const onlyResult = b.results.length === 1 ? b.results[0] : null;
  const score = b.published_score ?? onlyResult?.score;
  const metric = b.published_score != null ? b.metric_name : onlyResult?.metric_name || b.metric_name;
  return <article className="benchmark-row">
    <div className="benchmark-identity"><DatasetGlyph benchmark={b} /><div className="min-w-0">
      <h2>{candidate ? <span className="benchmark-title">{title}</span> : <Link className="benchmark-title" href={`/benchmarks/${encodeURIComponent(b.id)}`}>{title}</Link>}</h2>
      <p className="benchmark-description">{cleanDescription(b.description) || b.task_type?.replaceAll("_", " ") || "Source metadata is available for review."}</p>
      <div className="benchmark-meta"><span>{sourceLabel(b)}</span>{b.sample_count != null && <span>{b.sample_count.toLocaleString()} samples</span>}<span title={`${datasetAccess} · ${codeAccess}`}>{datasetAccess}</span></div>
    </div></div>
    <div><span className="mobile-fact-label">Published result</span>{b.results.length > 1 ? <><p className="benchmark-value">{b.results.length} results</p><p className="benchmark-value-label">Select during review</p></> : score != null ? <><p className="benchmark-value mono">{score}</p><p className="benchmark-value-label">{metric || "Metric not identified"}</p></> : <><p className="benchmark-value muted">—</p><p className="benchmark-value-label">{metric || "Not reported"}</p></>}</div>
    <div><span className="mobile-fact-label">Availability</span><span className={`status-badge ${b.compatibility.executable ? "success" : ""}`}><span className="status-dot" />{b.compatibility.executable ? "Ready to run" : "Specification only"}</span><p className="benchmark-value-label" title={missing.length ? `Missing: ${missing.join(", ")}` : "All required metadata identified"}>{b.readiness.score}/{b.readiness.total} metadata fields</p></div>
    <div className="benchmark-actions">{candidate ? <button className="btn" disabled={importing} onClick={onImport}>{importing ? "Importing…" : "Import"}</button> : <Link className="row-review" href={`/benchmarks/${encodeURIComponent(b.id)}/review`} aria-label={`Review ${title}`}>Review <Icon name="arrow" size={15} /></Link>}</div>
  </article>;
}

export default function Catalog() {
  const router = useRouter();
  const [items, setItems] = useState<Benchmark[]>([]);
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [domain, setDomain] = useState("");
  const [task, setTask] = useState("");
  const [metric, setMetric] = useState("");
  const [sort, setSort] = useState<NonNullable<CatalogQuery["sort"]>>("readiness");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [stale, setStale] = useState(false);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [candidates, setCandidates] = useState<{ query: string; items: Benchmark[] } | null>(null);
  const [importing, setImporting] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      benchmarkApi.catalog({ q, source, domain, task_type: task, metric, sort, limit: 24, offset }).then(data => {
        if (!active) return;
        setItems(data.items); setTotal(data.total); setError(""); setStale(data.stale);
      }).catch(e => { if (active) setError(e instanceof Error ? e.message : String(e)); }).finally(() => { if (active) setLoading(false); });
    }, 180);
    return () => { active = false; clearTimeout(timer); };
  }, [q, source, domain, task, metric, sort, offset, revision]);
  function update(setter: (value: string) => void, value: string) { setLoading(true); setOffset(0); setter(value); }
  function clearFilters() { setQ(""); setSource(""); setDomain(""); setTask(""); setMetric(""); setOffset(0); setLoading(true); setRevision(x => x + 1); }
  async function searchProvider() {
    if (!q.trim()) return;
    setSyncing(true); setError(""); setMessage("");
    try {
      const result = await benchmarkApi.sync({ provider: "huggingface", query: q.trim(), limit: 10 });
      const fresh = result.items.filter(b => b.saved === false);
      setCandidates({ query: q.trim(), items: fresh });
      setMessage(result.warnings.join(" ") || (fresh.length ? `${fresh.length} new match${fresh.length === 1 ? "" : "es"} on Hugging Face. Choose Import to add a benchmark.` : "No new matches on Hugging Face."));
      setLoading(true); setRevision(x => x + 1);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setSyncing(false); }
  }
  async function importCandidate(b: Benchmark) {
    const url = b.dataset_url || (b.dataset_identifier ? `https://huggingface.co/datasets/${b.dataset_identifier}` : null);
    if (!url) { setError("This result has no importable source URL."); return; }
    setImporting(b.id); setError("");
    try {
      const record = await benchmarkApi.importUrl(url);
      if (record.status === "failed" || !record.benchmark) { setError(record.warnings.join(" ") || "Import failed."); return; }
      router.push(`/benchmarks/${encodeURIComponent(record.benchmark.id)}/review`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setImporting(null); }
  }
  const activeFilters = [["Domain", domain], ["Task", task], ["Metric", metric]].filter(([, value]) => value);
  const hasFilters = !!(q || source || activeFilters.length);
  return <BenchmarkShell>
    <div className="page-header"><div><h1 className="page-heading">Benchmarks</h1><p className="page-subtitle">A starting point for your next experiment.</p></div><Link href="/benchmarks/import" className="btn btn-primary"><Icon name="plus" size={16} />Import benchmark</Link></div>
    <div className="catalog-tabs" role="group" aria-label="Filter by source">{[["", "All benchmarks"], ["huggingface", "Hugging Face"], ["openml", "OpenML"], ["github", "GitHub"], ["crossref", "Crossref"], ["arxiv", "arXiv"]].map(([value, label]) => <button key={value} className="catalog-tab" aria-pressed={source === value} onClick={() => { if (source !== value) update(setSource, value); }}>{label}</button>)}</div>
    <form className="catalog-toolbar" aria-label="Filter benchmarks" onSubmit={e => e.preventDefault()}>
      <label className="search-control"><Icon name="search" size={17} /><span className="sr-only">Search benchmarks</span><input type="search" value={q} onChange={e => update(setQ, e.target.value)} placeholder="Search benchmarks…" /></label>
      <button type="button" className="btn filter-toggle" aria-expanded={filtersOpen} aria-controls="catalog-filters" onClick={() => setFiltersOpen(open => !open)}><Icon name="filter" size={15} />Filters{activeFilters.length > 0 && <span className="text-teal">{activeFilters.length}</span>}</button>
      <label className="catalog-sort">Sort by<select value={sort} onChange={e => { setLoading(true); setOffset(0); setSort(e.target.value as NonNullable<CatalogQuery["sort"]>); }}><option value="readiness">Completeness</option><option value="newest">Newest</option><option value="smallest">Dataset size</option><option value="popular">Popularity</option></select></label>
    </form>
    {filtersOpen && <div id="catalog-filters" className="filter-panel">{([["Domain", domain, setDomain], ["Task type", task, setTask], ["Metric", metric, setMetric]] as const).map(([label, value, setter]) => <label key={label}>{label}<input className="form-control" value={value} onChange={e => update(setter, e.target.value)} placeholder={`Any ${label.toLowerCase()}`} /></label>)}</div>}
    {activeFilters.length > 0 && <div className="filter-summary">{activeFilters.map(([label, value]) => <span className="filter-chip" key={label}>{label}: {value}</span>)}<button className="link" onClick={clearFilters}>Clear filters</button></div>}
    {error && <Notice error><strong>Couldn’t load benchmarks.</strong> {error} <button className="underline" onClick={() => { setLoading(true); setRevision(x => x + 1); }}>Try again</button></Notice>}
    {stale && !error && <Notice>Showing saved metadata. Source details may have changed since the last import.</Notice>}
    <div className="catalog-table" aria-busy={loading}>
      <div className="catalog-table-heading" aria-hidden="true"><span>Benchmark<span className="result-count">{loading ? "…" : total}</span></span><span>Published result</span><span>Availability</span><span /></div>
      {loading && !items.length && !error ? Array.from({length: 4}, (_, i) => <div key={i} className="skeleton-row" aria-hidden="true"><div className="skeleton h-10 w-10" /><div className="flex-1"><div className="skeleton h-3 w-2/5" /><div className="skeleton mt-3 h-2 w-3/5" /></div></div>) : items.map(b => <BenchmarkRow key={b.id} b={b} />)}
      {!loading && !error && items.length === 0 && <div className="empty-state"><Icon name="search" size={25} /><h2>{hasFilters ? "No matching benchmarks" : "Your library starts here"}</h2><p>{hasFilters ? "Try another search or remove a filter to see more benchmarks." : "Import a dataset, repository, or paper to start reviewing a benchmark."}</p>{hasFilters ? <button className="btn" onClick={clearFilters}>Clear filters</button> : <Link className="btn" href="/benchmarks/import">Import benchmark</Link>}</div>}
    </div>
    <div className="catalog-footer"><p aria-live="polite">{loading ? "Updating benchmarks…" : `${total} benchmark${total === 1 ? "" : "s"}${hasFilters ? " matching your filters" : " in your library"}`}<span className="hidden sm:inline"> · Published scores retain their original evaluation protocol.</span></p>{total > 24 && <nav aria-label="Catalog pagination" className="catalog-pagination"><button className="btn" disabled={offset === 0 || loading} onClick={() => { setLoading(true); setOffset(x => Math.max(0, x - 24)); }}>Previous</button><span className="self-center">{offset + 1}–{Math.min(offset + 24, total)}</span><button className="btn" disabled={offset + 24 >= total || loading} onClick={() => { setLoading(true); setOffset(x => x + 24); }}>Next</button></nav>}</div>
    <div className="catalog-discovery"><Icon name="source" size={22} /><div><h2 className="section-title">Looking for something else?</h2><p>{q.trim() ? `Search Hugging Face for “${q.trim()}” to find benchmarks to import.` : "Search your library above, or import directly from a source URL."}</p></div>{q.trim() ? <button className="btn" disabled={syncing} onClick={searchProvider}>{syncing ? "Searching…" : "Search Hugging Face"}<Icon name="arrow" size={15} /></button> : <Link href="/benchmarks/import" className="btn">Import from URL<Icon name="arrow" size={15} /></Link>}</div>
    {message && <Notice>{message}</Notice>}
    {candidates && candidates.items.length > 0 && <section className="mt-7" aria-label="Hugging Face search results"><div className="mb-4 flex items-center justify-between gap-4"><h2 className="section-title">Hugging Face results for “{candidates.query}”</h2><button className="link text-xs" onClick={() => setCandidates(null)}>Dismiss</button></div><div className="catalog-table">{candidates.items.map(b => <BenchmarkRow key={b.id} b={b} candidate importing={importing === b.id} onImport={() => importCandidate(b)} />)}</div></section>}
  </BenchmarkShell>;
}

