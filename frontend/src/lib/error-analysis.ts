import type { Experiment } from "./api";
import { getComparisonContext } from "./experiment-comparison";

export type ErrorGroup = {
  group: string;
  count: number | null;
  positives: number | null;
  falseNegatives: number | null;
  falsePositives: number | null;
  recall: number | null;
  smallGroup: boolean;
};

export type ErrorGroupRow = {
  group: string;
  baseline: ErrorGroup | null;
  candidate: ErrorGroup | null;
  comparable: boolean;
  reasons: string[];
  changes: { falseNegatives: number | null; falsePositives: number | null; recall: number | null };
};

export type ErrorSort = "group" | "falseNegatives" | "falsePositives" | "recall" | "count" | "falseNegativesChange" | "falsePositivesChange" | "recallChange";

export function errorNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function count(value: unknown): number | null {
  const number = errorNumber(value);
  return number !== null && Number.isInteger(number) && number >= 0 ? number : null;
}

function rate(value: unknown): number | null {
  const number = errorNumber(value);
  return number !== null && number >= 0 && number <= 1 ? number : null;
}

function recordedGroups(experiment: Experiment | null, dimension: string): unknown[] {
  const groups = experiment?.result?.error_breakdowns?.[dimension];
  return Array.isArray(groups) ? groups : [];
}

export function errorDimensions(baseline: Experiment | null, candidate: Experiment | null): string[] {
  return [...new Set([baseline, candidate].flatMap(experiment => Object.keys(experiment?.result?.error_breakdowns ?? {}).filter(dimension => recordedGroups(experiment, dimension).length > 0)))].sort();
}

function indexGroups(experiment: Experiment | null, dimension: string) {
  const groups = new Map<string, ErrorGroup>();
  const duplicates = new Set<string>();
  for (const value of recordedGroups(experiment, dimension)) {
    if (!value || typeof value !== "object") continue;
    const row = value as Record<string, unknown>;
    if (typeof row.group !== "string") continue;
    if (groups.has(row.group)) { duplicates.add(row.group); continue; }
    const size = count(row.count);
    const positives = count(row.positives);
    const falseNegatives = count(row.false_negatives);
    const falsePositives = count(row.false_positives);
    const validPositives = size !== null && positives !== null && positives <= size ? positives : null;
    groups.set(row.group, {
      group: row.group,
      count: size,
      positives: validPositives,
      falseNegatives: validPositives !== null && falseNegatives !== null && falseNegatives <= validPositives ? falseNegatives : null,
      falsePositives: size !== null && validPositives !== null && falsePositives !== null && falsePositives <= size - validPositives ? falsePositives : null,
      recall: validPositives === 0 ? null : rate(row.recall),
      smallGroup: row.small_group === true || (size !== null && size < 30),
    });
  }
  return { groups, duplicates };
}

function difference(candidate: number | null, baseline: number | null): number | null {
  return candidate === null || baseline === null ? null : candidate - baseline;
}

/** Groups are matched by their recorded labels, never by their order or error rank. */
export function alignErrorGroups(baseline: Experiment | null, candidate: Experiment | null, dimension: string): ErrorGroupRow[] {
  const context = getComparisonContext(baseline, candidate);
  const left = indexGroups(baseline, dimension);
  const right = indexGroups(candidate, dimension);
  return [...new Set([...left.groups.keys(), ...right.groups.keys()])].map(group => {
    const a = left.groups.get(group) ?? null;
    const b = right.groups.get(group) ?? null;
    const reasons: string[] = [];
    if (!context.comparable) reasons.push(...context.reasons);
    if (!a) reasons.push("Group not recorded in the baseline.");
    if (!b) reasons.push("Group not recorded in the candidate.");
    if (left.duplicates.has(group) || right.duplicates.has(group)) reasons.push("Duplicate group labels make membership ambiguous.");
    if (a && b) {
      if (a.count === null || b.count === null || a.positives === null || b.positives === null) reasons.push("Group sample or positive counts are unknown.");
      else if (a.count !== b.count || a.positives !== b.positives) reasons.push("Group sample or positive counts differ; membership does not match.");
    }
    const comparable = context.comparable && reasons.length === 0;
    return {
      group, baseline: a, candidate: b, comparable, reasons,
      changes: {
        falseNegatives: comparable ? difference(b!.falseNegatives, a!.falseNegatives) : null,
        falsePositives: comparable ? difference(b!.falsePositives, a!.falsePositives) : null,
        recall: comparable ? difference(b!.recall, a!.recall) : null,
      },
    };
  });
}

export function filterErrorGroups(rows: ErrorGroupRow[], query: string): ErrorGroupRow[] {
  const search = query.trim().toLocaleLowerCase();
  return search ? rows.filter(row => row.group.toLocaleLowerCase().includes(search)) : rows;
}

/** Unknown values stay last in either direction; they never become zero or use the other run. */
export function sortErrorGroups(rows: ErrorGroupRow[], sort: ErrorSort, direction: "asc" | "desc", run: "baseline" | "candidate"): ErrorGroupRow[] {
  const value = (row: ErrorGroupRow): number | null => {
    if (sort === "falseNegativesChange") return row.changes.falseNegatives;
    if (sort === "falsePositivesChange") return row.changes.falsePositives;
    if (sort === "recallChange") return row.changes.recall;
    if (sort === "group") return null;
    return row[run]?.[sort] ?? null;
  };
  return [...rows].sort((a, b) => {
    const byGroup = a.group.localeCompare(b.group, undefined, { numeric: true });
    if (sort === "group") return direction === "asc" ? byGroup : -byGroup;
    const x = value(a); const y = value(b);
    if (x === null) return y === null ? byGroup : 1;
    if (y === null) return -1;
    return (direction === "asc" ? x - y : y - x) || byGroup;
  });
}

export function errorSummary(experiment: Experiment | null) {
  const result = experiment?.result;
  const matrix = result?.confusion_matrix;
  const values = { tp: count(matrix?.tp), fp: count(matrix?.fp), fn: count(matrix?.fn), tn: count(matrix?.tn) };
  const known = Object.values(values).every(value => value !== null);
  const total = known ? Object.values(values).reduce<number>((sum, value) => sum + (value ?? 0), 0) : null;
  const observations = count(result?.val_size);
  return { ...values, total, observations, threshold: rate(result?.threshold_best_f1), countMismatch: total !== null && observations !== null && total !== observations };
}
