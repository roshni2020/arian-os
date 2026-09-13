import type { Experiment } from "./api";

export type ContextCheck = {
  key: string;
  label: string;
  baseline: string | number | null;
  candidate: string | number | null;
  status: "match" | "mismatch" | "unknown";
};

export type ComparisonContext = {
  comparable: boolean;
  status: "matched" | "mismatch" | "unknown";
  reasons: string[];
  checks: ContextCheck[];
};

export function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function contextValue(value: unknown, numeric: boolean): string | number | null {
  if (numeric) {
    const number = finiteNumber(value);
    return number !== null && Number.isInteger(number) && number >= 0 ? number : null;
  }
  return typeof value === "string" && value.trim() ? value : null;
}

/** Matching validation contexts permit descriptive run-to-run differences, never a test benchmark claim. */
export function getComparisonContext(baseline: Experiment | null, candidate: Experiment | null): ComparisonContext {
  const fields = [
    ["session_id", "Session", baseline?.session_id, candidate?.session_id, false],
    ["score_kind", "Score kind", baseline?.result?.score_kind, candidate?.result?.score_kind, false],
    ["split", "Evaluation split", baseline?.result?.split, candidate?.result?.split, false],
    ["seed", "Seed", baseline?.result?.seed, candidate?.result?.seed, true],
    ["train_size", "Training samples", baseline?.result?.train_size, candidate?.result?.train_size, true],
    ["val_size", "Evaluation samples", baseline?.result?.val_size, candidate?.result?.val_size, true],
  ] as const;
  const checks: ContextCheck[] = fields.map(([key, label, before, after, numeric]) => {
    const baselineValue = contextValue(before, numeric);
    const candidateValue = contextValue(after, numeric);
    return { key, label, baseline: baselineValue, candidate: candidateValue, status: baselineValue === null || candidateValue === null ? "unknown" : baselineValue === candidateValue ? "match" : "mismatch" };
  });
  const status = checks.some(check => check.status === "mismatch") ? "mismatch" : checks.some(check => check.status === "unknown") ? "unknown" : "matched";
  const reasons = checks.filter(check => check.status !== "match").map(check => check.status === "unknown" ? `${check.label} is missing or invalid for ${check.baseline === null && check.candidate === null ? "both experiments" : check.baseline === null ? "the baseline" : "the candidate"}.` : `${check.label} differs (${check.baseline} versus ${check.candidate}).`);
  return { comparable: status === "matched", status, reasons, checks };
}

export const assessExperimentComparison = getComparisonContext;

type MetricDefinition = {
  id: string;
  label: string;
  direction: "higher" | "lower" | "neutral";
  unit: "score" | "seconds" | "count";
  thresholded?: boolean;
  read: (experiment: Experiment | null) => unknown;
};

const metricDefinitions: MetricDefinition[] = [
  { id: "ap", label: "Average precision (AP)", direction: "higher", unit: "score", read: exp => exp?.result?.validation_auprc },
  { id: "auroc", label: "AUROC", direction: "higher", unit: "score", read: exp => exp?.result?.validation_auroc },
  { id: "train_ap", label: "Training AP", direction: "neutral", unit: "score", read: exp => exp?.result?.train_auprc },
  { id: "precision", label: "Precision", direction: "higher", unit: "score", thresholded: true, read: exp => exp?.result?.validation_metrics?.precision },
  { id: "recall", label: "Recall", direction: "higher", unit: "score", thresholded: true, read: exp => exp?.result?.validation_metrics?.recall },
  { id: "f1", label: "F1", direction: "higher", unit: "score", thresholded: true, read: exp => exp?.result?.validation_metrics?.f1 },
  { id: "threshold", label: "Best-F1 threshold", direction: "neutral", unit: "score", read: exp => exp?.result?.threshold_best_f1 },
  { id: "runtime", label: "Runtime", direction: "lower", unit: "seconds", read: exp => finiteNumber(exp?.result?.runtime_seconds) ?? exp?.runtime_seconds },
  { id: "features", label: "Features", direction: "neutral", unit: "count", read: exp => exp?.result?.n_features },
];

export type ComparisonMetric = Omit<MetricDefinition, "read"> & {
  baseline: number | null;
  candidate: number | null;
  difference: number | null;
};

export function getComparisonMetrics(baseline: Experiment | null, candidate: Experiment | null): ComparisonMetric[] {
  const { comparable } = getComparisonContext(baseline, candidate);
  return metricDefinitions.map(({ read, ...definition }) => {
    const before = finiteNumber(read(baseline));
    const after = finiteNumber(read(candidate));
    return { ...definition, baseline: before, candidate: after, difference: comparable && before !== null && after !== null ? finiteNumber(after - before) : null };
  });
}

export function formatComparisonValue(value: number | null, unit: ComparisonMetric["unit"]): string {
  if (value === null || !Number.isFinite(value)) return "Not available";
  if (unit === "count") return value.toLocaleString("en-US");
  return `${value.toFixed(unit === "seconds" ? 1 : 4)}${unit === "seconds" ? " s" : ""}`;
}

export function formatComparisonDifference(value: number | null, unit: ComparisonMetric["unit"]): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const precision = unit === "count" ? 0 : unit === "seconds" ? 1 : 4;
  const rounded = Number(value.toFixed(precision));
  if (rounded === 0 && value !== 0) return `${value > 0 ? "+" : "−"}${Math.abs(value).toPrecision(2)}${unit === "seconds" ? " s" : ""}`;
  return `${rounded > 0 ? "+" : rounded < 0 ? "−" : ""}${formatComparisonValue(Math.abs(rounded), unit)}`;
}

export type ConfigurationDifference = { path: string; baseline: unknown; candidate: unknown };

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function equivalent(before: unknown, after: unknown): boolean {
  if (Object.is(before, after)) return true;
  if (Array.isArray(before) && Array.isArray(after)) return before.length === after.length && before.every((item, i) => equivalent(item, after[i]));
  if (isRecord(before) && isRecord(after)) {
    const keys = Object.keys(before);
    return keys.length === Object.keys(after).length && keys.every(key => Object.hasOwn(after, key) && equivalent(before[key], after[key]));
  }
  return false;
}

export function getConfigurationDifferences(baseline: Experiment | null, candidate: Experiment | null): ConfigurationDifference[] {
  if (!baseline || !candidate) return [];
  const differences: ConfigurationDifference[] = [];
  function walk(before: unknown, after: unknown, path: string) {
    if (equivalent(before, after)) return;
    if ((isRecord(before) || before === undefined) && (isRecord(after) || after === undefined) && (isRecord(before) || isRecord(after))) {
      const left = isRecord(before) ? before : {};
      const right = isRecord(after) ? after : {};
      const keys = [...new Set([...Object.keys(left), ...Object.keys(right)])].sort();
      if (keys.length) { keys.forEach(key => walk(left[key], right[key], path ? `${path}.${key}` : key)); return; }
    }
    differences.push({ path: path || "Configuration", baseline: before, candidate: after });
  }
  walk(baseline.experiment, candidate.experiment, "");
  return differences;
}

export function formatConfigurationValue(value: unknown): string {
  if (value === undefined) return "Not set";
  if (typeof value === "string") return value || '""';
  return JSON.stringify(value) ?? "Not set";
}

export type PrecisionRecallPoint = { recall: number; precision: number };

export function getPrecisionRecallPoints(experiment: Experiment | null): { points: PrecisionRecallPoint[]; rejected: number } {
  const recorded = experiment?.result?.pr_curve;
  if (!Array.isArray(recorded)) return { points: [], rejected: 0 };
  const points: PrecisionRecallPoint[] = [];
  let rejected = 0;
  for (const item of recorded) {
    const recall = finiteNumber(item?.recall);
    const precision = finiteNumber(item?.precision);
    if (recall === null || precision === null || recall < 0 || recall > 1 || precision < 0 || precision > 1) rejected += 1;
    else points.push({ recall, precision });
  }
  return { points, rejected };
}
