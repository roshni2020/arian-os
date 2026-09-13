import type { Benchmark } from "./benchmarks";

export const reviewFields = ["dataset_provider", "dataset_identifier", "dataset_url", "dataset_revision", "repository_url", "task_type", "metric_name", "metric_direction", "published_score", "published_model", "train_split", "validation_split", "test_split", "evaluation_protocol", "leakage_notes"] as const;
export type ReviewValues = Record<(typeof reviewFields)[number], string>;
export function selectedReviewBenchmark(b: Benchmark, selected: string): Benchmark {
  const result = b.results.find(item => item.id === selected);
  if (!result) return b;
  const updated = { ...b, provenance: { ...b.provenance }, metric_name: result.metric_name, metric_direction: result.metric_direction, published_score: result.score, published_model: result.model };
  for (const field of ["metric_name", "metric_direction", "published_score", "published_model"] as const) {
    if (updated[field] !== b[field]) updated.provenance[field] = { value: updated[field], source_provider: null, source_url: result.source_url, status: updated[field] == null ? "missing" : "inferred", confidence: null };
  }
  return updated;
}
export function reviewValues(b: Benchmark): ReviewValues {
  return Object.fromEntries(reviewFields.map(field => [field, b[field] == null ? "" : typeof b[field] === "object" ? JSON.stringify(b[field], null, 2) : String(b[field])])) as ReviewValues;
}
export function reviewOverrides(b: Benchmark, values: ReviewValues): Record<string, unknown> {
  const original = reviewValues(b);
  const overrides: Record<string, unknown> = {};
  for (const field of reviewFields) {
    if (values[field] === original[field]) continue;
    const value = values[field].trim();
    if (!value) { overrides[field] = null; continue; }
    if (field === "published_score") {
      const score = Number(value);
      if (!Number.isFinite(score)) throw new Error("Published target must be a finite number.");
      overrides[field] = score;
    } else if (field === "evaluation_protocol") {
      let parsed: unknown;
      try { parsed = JSON.parse(value); } catch { throw new Error("Evaluation protocol must be a valid JSON object."); }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Evaluation protocol must be a JSON object.");
      overrides[field] = parsed;
    } else overrides[field] = value;
  }
  return overrides;
}
