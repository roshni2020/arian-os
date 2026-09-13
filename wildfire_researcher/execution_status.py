"""Read-only execution observations; no worker control or remote polling.

Persisted status and recent activity are not a heartbeat. The API process can
observe its own worker thread, not a CLI worker, Launch agent, or cloud queue.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote

STALE_AFTER_SECONDS = 900
EVENT_LIMIT = 20
FEEDBACK_LIMIT = 10
TERMINAL = {"complete", "cancelled", "error"}
STAGES = {
    "created": "idle", "running_baseline": "training", "training": "training",
    "awaiting_aria_proposal": "waiting_for_aria", "awaiting_final_decision": "waiting_for_aria",
    "validating_proposal": "validating", "evaluating": "evaluating",
    "final_evaluation": "finalizing", "complete": "terminal",
    "cancelled": "terminal", "error": "terminal",
}


class ExecutionStatusUnavailable(RuntimeError):
    pass


def _object(value):
    try:
        result = json.loads(value) if isinstance(value, str) else value
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def _text(value, limit=1200):
    return value[:limit] if isinstance(value, str) else None


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _latest(*values):
    valid = [(parsed, value) for value in values if (parsed := _time(value)) is not None]
    return max(valid, key=lambda entry: entry[0])[1] if valid else None


def _snapshot(path, session_id):
    """Bounded projections from a read-only connection; never initialize Store."""
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            row = db.execute("SELECT id,status,aria_mode,budget,state_revision,created_at,updated_at,"
                             "cancel_requested,protocol_json,wandb_entity,wandb_project FROM sessions WHERE id=?",
                             (session_id,)).fetchone()
            if row is None:
                raise KeyError(session_id)
            session = dict(row)
            latest_event = db.execute("SELECT ts FROM events WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
            events = [dict(row) for row in db.execute(
                "SELECT id,ts,kind,message FROM events WHERE session_id=? AND kind NOT IN ('waiting','traceback') "
                "ORDER BY id DESC LIMIT ?", (session_id, EVENT_LIMIT))]
            messages = [dict(row) for row in db.execute(
                "SELECT id,ts,kind,state_revision,accepted,artifact_ref,feedback_json FROM aria_messages "
                "WHERE session_id=? AND direction='inbound' ORDER BY id DESC LIMIT ?", (session_id, FEEDBACK_LIMIT))]
            latest_message = db.execute("SELECT ts FROM aria_messages WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
            completed = db.execute("SELECT count(*) FROM experiments WHERE session_id=? AND status='complete'", (session_id,)).fetchone()[0]
            # A first training/evaluation status is stronger evidence than creation.
            start_rows = db.execute("SELECT ts,payload_json FROM events WHERE session_id=? AND kind='status' ORDER BY id LIMIT 50", (session_id,)).fetchall()
            started_at = next((row["ts"] for row in start_rows if _object(row["payload_json"]).get("status") in {
                "running_baseline", "training", "evaluating", "validating_proposal", "final_evaluation"
            }), None)
            return session, events, messages, completed, started_at, latest_event[0] if latest_event else None, latest_message[0] if latest_message else None
    except sqlite3.Error:
        raise ExecutionStatusUnavailable("Execution status is temporarily unavailable") from None


def _launch_refs(operations_dir, session_id):
    """Setup references only; a saved agent_status never establishes liveness."""
    if operations_dir is None:
        return None
    path = Path(operations_dir) / "launch" / "setup.json"
    try:
        with path.open("rb") as file:
            raw = file.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            return None
        data = _object(raw.decode("utf-8"))
        if data.get("session_id") != session_id:
            return None
        return {key: _text(data.get(key), 300) for key in
                ("queue", "job", "baseline_queue_item_id", "source_fingerprint")}
    except (OSError, UnicodeError):
        return None


def _recovery(session, transport, alive, registered):
    status = session["status"]
    result = {"resume_available": False, "cancel_available": False,
              "action": "none", "reason": "The session is complete; there is no pending execution to resume."}
    if session["aria_mode"] == "replay":
        result["reason"] = "Replay is a stored record; it does not run or resume research."
    elif transport == "wandb-launch":
        result.update(action="inspect_external", reason=(
            "This session uses W&B Launch. Inspect the queue and ARIA controller in W&B; local Resume is unsupported. "
            "Saved Launch references do not establish current queue or agent health."
        ))
        result["cancel_available"] = status not in TERMINAL and not session["cancel_requested"]
        if result["cancel_available"]:
            result["reason"] += " Cancel requests cooperative cancellation; it does not remove queued Launch jobs."
    elif status == "complete":
        pass
    elif status in TERMINAL and alive is True:
        result["reason"] = "The recorded session is terminal, but its local thread is still alive. Allow it to finish before attempting recovery."
    elif alive is True:
        result.update(cancel_available=not session["cancel_requested"], reason=(
            "A worker thread is alive in this API process. Cancel requests cooperative cancellation; Resume is unavailable while it is alive."
        ))
    elif status in {"error", "cancelled"} or (registered and alive is False and status != "created"):
        result.update(resume_available=True, action="resume", reason=(
            "Manual local Resume is available for this recorded session state. No live worker is observed in this API process. "
            "A CLI worker in another process is not observable here; check it before resuming. The worker lock can reject a conflicting start."
        ))
    else:
        result.update(action="inspect_local", cancel_available=status != "created" and not session["cancel_requested"], reason=(
            "No live worker is observed in this API process. A CLI worker may still be active; absence here is not evidence that execution stopped. "
            "Inspect the event history and worker host before starting another worker."
        ))
    if session["cancel_requested"] and status not in TERMINAL:
        result["reason"] += " Cancellation has already been requested."
    return result


def execution_status(store, session_id, *, local_worker=None, now=None, operations_dir=None):
    """Return local persisted evidence and scoped observations without side effects."""
    session, events, messages, completed, started_at, last_event_at, last_message_at = _snapshot(store.path, session_id)
    now = now or datetime.now(timezone.utc)
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    protocol = _object(session.pop("protocol_json"))
    transport = "wandb-launch" if protocol.get("execution_backend") == "wandb-launch" else "local"
    terminal = session["status"] in TERMINAL or session["aria_mode"] == "replay"
    registered = local_worker is not None
    alive = bool(local_worker.is_alive()) if registered else None
    last_updated_at = _latest(session["updated_at"], last_event_at, last_message_at)
    # Keep execution activity distinct from administrative/session-row updates.
    # age_seconds always describes this exact timestamp, never the poll time.
    last_activity_at = _latest(last_event_at, last_message_at)
    activity_time = _time(last_activity_at)
    age = max(0, int((now - activity_time).total_seconds())) if activity_time else None
    if terminal:
        activity_state = "terminal"
        detail = "The recorded session is terminal; an execution heartbeat is not expected."
    elif activity_time is None:
        activity_state = "no_heartbeat"
        detail = "No execution activity has been recorded. Worker and queue heartbeats are not available."
    elif age >= STALE_AFTER_SECONDS:
        activity_state = "stale"
        detail = "No recent activity is recorded. This is not proof that a CLI worker, Launch agent, or training process has stopped."
    else:
        activity_state = "recent"
        detail = "Recent activity is recorded; event recency does not establish external worker or queue health."
    feedback = []
    for message in messages:
        item = {key: message[key] for key in ("id", "ts", "kind", "state_revision")}
        item["accepted"] = None if message["accepted"] is None else bool(message["accepted"])
        item["artifact_ref"] = _text(message["artifact_ref"], 500)
        fields = _object(message["feedback_json"])
        item["feedback"] = {"code": _text(fields.get("code"), 100), "message": _text(fields.get("message"))} if fields else None
        feedback.append(item)
    for event in events:
        event["message"] = _text(event["message"])
    entity, project = session.get("wandb_entity"), session.get("wandb_project")
    base = f"https://wandb.ai/{quote(entity, safe='')}/{quote(project, safe='')}" if isinstance(entity, str) and entity and isinstance(project, str) and project else None
    used = max(0, completed - 1)  # Match research_state: fixed baseline excluded.
    return {
        "session_id": session_id, "transport": transport, "status": session["status"],
        "stage": STAGES.get(session["status"], "unknown"), "terminal": terminal,
        "observed_at": now.isoformat(), "created_at": session["created_at"], "started_at": started_at,
        "last_event_at": last_event_at, "last_activity_at": last_activity_at, "last_updated_at": last_updated_at,
        "activity": {"state": activity_state, "age_seconds": age, "stale_after_seconds": STALE_AFTER_SECONDS, "detail": detail},
        "local_worker": {"registered": registered, "alive": alive, "scope": "this_api_process"},
        "remote": {"heartbeat_at": None, "queue_state": None, "verified": False,
                   "detail": "No remote refresh is performed. CLI workers, Launch agents and queue state are not observed by this endpoint."},
        "budget": {"max": session["budget"], "used": used, "remaining": max(0, session["budget"] - used), "baseline_excluded": True},
        "events": events, "proposal_feedback": feedback,
        "launch_refs": _launch_refs(operations_dir, session_id) if transport == "wandb-launch" else None,
        "links": {"project": base, "launch": f"https://wandb.ai/{quote(entity, safe='')}/launch" if base else None,
                  "traces": base + "/weave/traces" if base else None},
        "recovery": _recovery(session, transport, alive, registered),
    }
