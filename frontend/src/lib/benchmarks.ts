export type Provenance = { value: unknown; source_provider: string | null; source_url: string | null; status: "verified" | "inferred" | "missing" | "user_edited"; confidence: "high" | "medium" | "low" | null };
export type Source = { provider: string; external_id: string | null; external_url: string | null; last_synced_at: string | null };
export type Result = { id: string; model: string | null; metric_name: string | null; metric_direction: string | null; metric_definition: string | null; score: number | null; dataset_identifier: string | null; dataset_revision: string | null; split: string | null; source_url: string | null };
export type Readiness = { status: "complete" | "partial"; score: number; total: 6; missing: string[] };
export type Compatibility = { executable: boolean; executor: "wildfireia" | null; reasons: string[]; comparability: string };
export type Benchmark = {
  id: string; slug: string; title: string; description: string | null; domain: string | null; task_type: string | null;
  publication_date: string | null; paper_url: string | null; repository_url: string | null; dataset_url: string | null;
  dataset_provider: string | null; dataset_identifier: string | null; dataset_revision: string | null;
  dataset_public: boolean | null; repository_public: boolean | null;
  metric_name: string | null; metric_direction: string | null; published_score: number | null; published_model: string | null;
  sample_count: number | null; license: string | null; train_split: string | null; validation_split: string | null; test_split: string | null;
  evaluation_protocol: Record<string, unknown> | null; leakage_notes: string | null; source: string | null; created_at: string; updated_at: string;
  provenance: Record<string, Provenance>; sources: Source[]; results: Result[]; readiness: Readiness; compatibility: Compatibility;
  /** false only on unsaved search candidates returned by sync; absent on library records */
  saved?: boolean;
};
export type Project = { id: string; name: string; benchmark_id: string; snapshot: Benchmark; experiment_budget: number; selected_result_id: string | null; session_id: string | null; created_at: string; compatibility: Compatibility };
export type ImportRecord = { id: string; status: "complete" | "partial" | "failed"; benchmark: Benchmark | null; warnings: string[] };
export type CatalogQuery = { q?: string; source?: string; domain?: string; task_type?: string; metric?: string; sort?: "newest" | "readiness" | "smallest" | "popular"; limit?: number; offset?: number };
export type CreateProjectInput = { benchmark_id: string; name: string; experiment_budget: number; overrides?: Record<string, unknown>; selected_result_id?: string; idempotency_key?: string };
export type StartResponse = { project: Project; session_id: string; journal_url: string };

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, { cache: "no-store", ...(body === undefined ? {} : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }) });
  if (!response.ok) {
    let message = `Request failed (${response.status}). Please try again.`;
    try { const payload = await response.json(); if (typeof payload.detail === "string") message = payload.detail; } catch { /* Keep a safe error for non-JSON proxy responses. */ }
    throw new Error(message);
  }
  return response.json();
}

export const benchmarkApi = {
  catalog: (query: CatalogQuery = {}) => {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
    return request<{ items: Benchmark[]; total: number; stale: boolean }>(`/benchmarks${params.size ? `?${params}` : ""}`);
  },
  get: (id: string) => request<Benchmark>(`/benchmarks/${encodeURIComponent(id)}`),
  sync: (body: { provider: "huggingface" | "openml"; query: string; limit: number }) => request<{ items: Benchmark[]; warnings: string[] }>("/benchmarks/sync", body),
  importUrl: (url: string) => request<ImportRecord>("/benchmarks/import", { url }),
  getImport: (id: string) => request<ImportRecord>(`/benchmarks/imports/${encodeURIComponent(id)}`),
  createProject: (body: CreateProjectInput) => request<Project>("/projects", body),
  projects: () => request<{ items: Project[] }>("/projects"),
  project: (id: string) => request<Project>(`/projects/${encodeURIComponent(id)}`),
  start: (id: string) => request<StartResponse>(`/projects/${encodeURIComponent(id)}/start`, {}),
};

export function safeJournalUrl(value: string): string | null {
  if (!value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u0020]/.test(value)) return null;
  try { const parsed = new URL(value, "http://local.invalid"); return parsed.origin === "http://local.invalid" ? `${parsed.pathname}${parsed.search}${parsed.hash}` : null; } catch { return null; }
}
export function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not available";
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}
export function displayAccess(value: boolean | null | undefined): string {
  return value === true ? "Public access confirmed" : value === false ? "Restricted access" : "Access not confirmed";
}
