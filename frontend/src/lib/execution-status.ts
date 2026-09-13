import type { EventRow } from "./api";

export type ExecutionStatus = {
  session_id: string;
  transport: "local" | "wandb-launch";
  status: string;
  stage: string;
  terminal: boolean;
  observed_at: string;
  created_at: string;
  started_at: string | null;
  last_event_at: string | null;
  last_activity_at: string | null;
  last_updated_at: string | null;
  activity: { state: "recent" | "stale" | "no_heartbeat" | "terminal"; age_seconds: number | null; stale_after_seconds: number; detail: string };
  local_worker: { registered: boolean; alive: boolean | null; scope: string };
  remote: { heartbeat_at: string | null; queue_state: string | null; verified: boolean; detail: string };
  budget: { max: number; used: number; remaining: number; baseline_excluded: boolean };
  events: Pick<EventRow, "id" | "ts" | "kind" | "message">[];
  proposal_feedback: { id: number; ts: string; kind: string; state_revision: number | null; accepted: boolean | null; artifact_ref: string | null; feedback: { code: string | null; message: string | null } | null }[];
  launch_refs: { queue: string | null; job: string | null; baseline_queue_item_id: string | null; source_fingerprint: string | null } | null;
  links: { project: string | null; launch: string | null; traces: string | null };
  recovery: { resume_available: boolean; cancel_available: boolean; action: string; reason: string };
};

export function elapsedLabel(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "Not recorded";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor(seconds % 86400 / 3600)}h`;
}

export function safeWandbLink(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "wandb.ai" && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export async function fetchExecutionStatus(sessionId: string): Promise<ExecutionStatus> {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/execution-status`, { cache: "no-store" });
  if (!response.ok) throw new Error(response.status === 404 ? "Execution details are unavailable. The API may need to be updated, or the session no longer exists." : "Execution status could not be refreshed. Try again.");
  return response.json();
}
