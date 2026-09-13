import type { Experiment } from "./api";

export type AnalysisRecordIdentity = Pick<Experiment, "id" | "session_id" | "updated_at">;

export function analysisCacheKey(sessionId: string, id: string): string {
  return JSON.stringify([sessionId, id]);
}

/** A full live response may be newer than a polling summary, but never older or from another source. */
export function acceptAnalysisRecord(record: Experiment, expected: AnalysisRecordIdentity): boolean {
  if (record.id !== expected.id || record.session_id !== expected.session_id) return false;
  if (!record.updated_at || !expected.updated_at) return false;
  if (record.updated_at === expected.updated_at) return true;
  const receivedAt = Date.parse(record.updated_at);
  const expectedAt = Date.parse(expected.updated_at);
  return Number.isFinite(receivedAt) && Number.isFinite(expectedAt) && receivedAt >= expectedAt;
}

export function cachedAnalysisRecord(summary: Experiment | null, sessionId: string, cache: Record<string, Experiment>): Experiment | null {
  if (!summary || summary.session_id !== sessionId) return null;
  const record = cache[analysisCacheKey(sessionId, summary.id)];
  return record && acceptAnalysisRecord(record, summary) ? record : null;
}

export function analysisRecordForView(summary: Experiment | null, sessionId: string, cache: Record<string, Experiment>, replay: boolean): Experiment | null {
  if (!summary || summary.session_id !== sessionId) return null;
  return replay ? summary : cachedAnalysisRecord(summary, sessionId, cache) || summary;
}

export function resolveAnalysisSelection(experiments: Experiment[], sessionId: string, pinnedId: string, candidateId: string) {
  const available = experiments.filter(exp => exp.result && exp.session_id === sessionId).sort((a, b) => a.iteration - b.iteration || a.id.localeCompare(b.id));
  const baseline = pinnedId ? available.find(exp => exp.id === pinnedId) || null : available[0] || null;
  const alternatives = available.filter(exp => exp.id !== baseline?.id);
  const candidate = candidateId ? alternatives.find(exp => exp.id === candidateId) || null : [...alternatives].sort((a, b) => {
    const scoreA = typeof a.score === "number" && Number.isFinite(a.score) ? a.score : -Infinity;
    const scoreB = typeof b.score === "number" && Number.isFinite(b.score) ? b.score : -Infinity;
    return scoreA === scoreB ? a.iteration - b.iteration || a.id.localeCompare(b.id) : scoreB - scoreA;
  })[0] || null;
  return { available, baseline, candidate };
}
