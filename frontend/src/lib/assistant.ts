export type AssistantKind = "ask" | "error_proposal" | "study_plan" | "report";
export type Evidence = { id: string; session_id?: string; experiment_id?: string; path: string; value: unknown };
export type AssistantRequest = {
  id: string; kind: AssistantKind; status: string; question: string; created_at: string;
  session_id?: string; project_id?: string; error?: unknown; error_detail?:unknown;
  provenance?: { transport?:string; aria_verified?:boolean; artifact_ref?:string } | null;
  snapshot: { id: string; hash: string; evidence: Evidence[] };
  response?: { claims: { text: string; citations: string[] }[]; assumptions: string[]; missing_evidence: string[]; draft: Record<string, unknown> | null } | null;
};
export type Capabilities = { verified: boolean; reason: string; [key: string]: unknown };
export const pendingRequest = (status: string) => ["queued", "dispatched", "waiting"].includes(status);
export function errorText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.message;
  if (value && typeof value === "object" && "message" in value) return String(value.message);
  return JSON.stringify(value) || "Request failed";
}
export async function assistantApi<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/assistant${path}`, {
    cache: "no-store", ...(body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail ? errorText(data.detail) : `Assistant request failed (${response.status}).`);
  return data as T;
}
export function scopeQuery(sessionId?: string, projectId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set("session_id", sessionId);
  if (projectId) query.set("project_id", projectId);
  return query.toString();
}
/** Keep this key unchanged when retrying an uncertain submission. */
export function submissionKey() { return crypto.randomUUID(); }
export function seedList(input: string) {
  const seeds = input.split(",").map(s => Number(s.trim()));
  if (!input.trim() || input.split(",").some(s => !s.trim()) || seeds.some(s => !Number.isSafeInteger(s) || s < 0) || new Set(seeds).size !== seeds.length) throw new Error("Enter distinct, non-negative integer seeds separated by commas.");
  return seeds;
}
