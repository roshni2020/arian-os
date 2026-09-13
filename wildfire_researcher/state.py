"""Durable research state: SQLite persistence plus the JSON research state shared with ARIA.

The store is the source of truth. `research_state()` renders what ARIA and the UI see; it never
includes test-split results, secrets, or anything ARIA did not actually produce.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import config, protocol
from .experiments import capability_manifest

STATUSES = [
    "created",
    "running_baseline",
    "awaiting_aria_proposal",
    "validating_proposal",
    "training",
    "evaluating",
    "awaiting_final_decision",
    "final_evaluation",
    "complete",
    "cancelled",
    "error",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_session_id(prefix: str = "wf") -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS final_evaluation_freezes (
  session_id TEXT PRIMARY KEY,
  frozen_at TEXT NOT NULL,
  identity_json TEXT NOT NULL,
  prior_test_exposure_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL,
  aria_mode TEXT NOT NULL,
  target_metric TEXT NOT NULL,
  target_value REAL NOT NULL,
  budget INTEGER NOT NULL,
  research_seed INTEGER NOT NULL,
  state_revision INTEGER NOT NULL DEFAULT 0,
  fast_mode INTEGER NOT NULL DEFAULT 0,
  limit_train_samples INTEGER,
  wandb_entity TEXT,
  wandb_project TEXT,
  current_best_experiment_id TEXT,
  current_best_auprc REAL,
  final_decision_json TEXT,
  final_evaluation_json TEXT,
  error TEXT,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  protocol_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
  id TEXT NOT NULL,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  iteration INTEGER NOT NULL,
  parent_experiment_id TEXT,
  config_key TEXT NOT NULL,
  status TEXT NOT NULL,
  controller TEXT NOT NULL,
  proposal_json TEXT,
  proposal_source TEXT,
  experiment_json TEXT NOT NULL,
  change_summary TEXT,
  result_json TEXT,
  score REAL,
  previous_best REAL,
  delta REAL,
  decision TEXT,
  decision_reason TEXT,
  decision_learning TEXT,
  next_question TEXT,
  decision_source TEXT,
  runtime_seconds REAL,
  wandb_run_id TEXT,
  wandb_run_url TEXT,
  weave_trace_id TEXT,
  weave_trace_url TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (session_id, id),
  UNIQUE(session_id, iteration),
  UNIQUE(session_id, config_key)
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  payload_json TEXT
);
CREATE TABLE IF NOT EXISTS aria_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  direction TEXT NOT NULL,
  kind TEXT NOT NULL,
  artifact_ref TEXT,
  artifact_digest TEXT,
  state_revision INTEGER,
  accepted INTEGER,
  feedback_json TEXT,
  payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);
CREATE INDEX IF NOT EXISTS idx_exp_session ON experiments(session_id, iteration);
"""


def _loads(value: str | None) -> Any:
    return json.loads(value) if value else None


class Store:
    """Thin SQLite wrapper. One store per process; connections are per-thread."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or config.DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._migrate_experiments_pk()
        self._raw().executescript(SCHEMA)

    def _migrate_experiments_pk(self) -> None:
        """Early databases keyed experiments by id alone; re-key by (session_id, id)."""
        conn = self._raw()
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='experiments'").fetchone()
        if row is None or "PRIMARY KEY (session_id, id)" in row[0]:
            return
        conn.executescript(
            "BEGIN; ALTER TABLE experiments RENAME TO experiments_old; "
            + SCHEMA
            + "INSERT INTO experiments SELECT * FROM experiments_old; DROP TABLE experiments_old; COMMIT;"
        )

    def _raw(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = self._raw()
        if conn.in_transaction:  # nested use inside an outer transaction
            yield conn
            return
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    # ---- sessions -------------------------------------------------------------------
    def create_session(self, *, session_id: str | None = None, budget: int, aria_mode: str, research_seed: int, fast_mode: bool, limit_train_samples: int | None, entity: str, project: str) -> dict[str, Any]:
        sid = session_id or new_session_id()
        ts = now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, created_at, updated_at, status, aria_mode, target_metric, target_value, budget, research_seed, state_revision, fast_mode, limit_train_samples, wandb_entity, wandb_project, protocol_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sid, ts, ts, "created", aria_mode, "test_auprc", config.TARGET_AUPRC, budget, research_seed, 0, int(fast_mode), limit_train_samples, entity, project, json.dumps(protocol.provenance())),
            )
        self.log_event(sid, "session_created", f"Session {sid} created (budget {budget}, ARIA mode {aria_mode})")
        return self.get_session(sid)

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown session {session_id}")
        d = dict(row)
        d["protocol"] = _loads(d.pop("protocol_json"))
        d["final_decision"] = _loads(d.pop("final_decision_json"))
        d["final_evaluation"] = _loads(d.pop("final_evaluation_json"))
        d["fast_mode"] = bool(d["fast_mode"])
        d["cancel_requested"] = bool(d["cancel_requested"])
        return d

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id FROM sessions ORDER BY created_at DESC").fetchall()
        return [self.get_session(r["id"]) for r in rows]

    def update_session(self, session_id: str, **fields: Any) -> None:
        if not fields:
            return
        encoded = {}
        for k, v in fields.items():
            if k in {"final_decision", "final_evaluation"}:
                encoded[k + "_json"] = json.dumps(v)
            elif isinstance(v, bool):
                encoded[k] = int(v)
            else:
                encoded[k] = v
        encoded["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in encoded)
        with self.connect() as conn:
            conn.execute(f"UPDATE sessions SET {cols} WHERE id=?", (*encoded.values(), session_id))

    def set_status(self, session_id: str, status: str, message: str | None = None) -> None:
        assert status in STATUSES, status
        self.update_session(session_id, status=status)
        self.log_event(session_id, "status", message or f"Status -> {status}", {"status": status})

    def bump_revision(self, session_id: str) -> int:
        with self.connect() as conn:
            conn.execute("UPDATE sessions SET state_revision = state_revision + 1, updated_at=? WHERE id=?", (now(), session_id))
            rev = conn.execute("SELECT state_revision FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
        return int(rev)

    # ---- experiments ------------------------------------------------------------------
    def claim_experiment(self, session_id: str, *, experiment: dict[str, Any], config_key: str, controller: str, proposal: dict[str, Any] | None, proposal_source: str | None, parent_experiment_id: str | None, change_summary: str) -> dict[str, Any]:
        """Transactionally create the next experiment row. A duplicate config_key raises."""
        ts = now()
        with self.connect() as conn:
            iteration = conn.execute("SELECT COALESCE(MAX(iteration), -1) + 1 FROM experiments WHERE session_id=?", (session_id,)).fetchone()[0]
            exp_id = f"exp-{iteration:03d}"
            conn.execute(
                "INSERT INTO experiments (id, session_id, iteration, parent_experiment_id, config_key, status, controller, proposal_json, proposal_source, experiment_json, change_summary, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (exp_id, session_id, iteration, parent_experiment_id, config_key, "claimed", controller, json.dumps(proposal) if proposal else None, proposal_source, json.dumps(experiment), change_summary, ts, ts),
            )
        return self.get_experiment(session_id, exp_id)

    def update_experiment(self, session_id: str, experiment_id: str, **fields: Any) -> None:
        encoded = {}
        for k, v in fields.items():
            if k in {"result", "proposal"}:
                encoded[k + "_json"] = json.dumps(v)
            else:
                encoded[k] = v
        encoded["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in encoded)
        with self.connect() as conn:
            conn.execute(f"UPDATE experiments SET {cols} WHERE session_id=? AND id=?", (*encoded.values(), session_id, experiment_id))

    def get_experiment(self, session_id: str, experiment_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM experiments WHERE session_id=? AND id=?", (session_id, experiment_id)).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        return self._exp_row(row)

    def _exp_row(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["experiment"] = _loads(d.pop("experiment_json"))
        d["proposal"] = _loads(d.pop("proposal_json"))
        d["result"] = _loads(d.pop("result_json"))
        return d

    def experiments(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM experiments WHERE session_id=? ORDER BY iteration", (session_id,)).fetchall()
        return [self._exp_row(r) for r in rows]

    def completed_experiments(self, session_id: str) -> list[dict[str, Any]]:
        return [e for e in self.experiments(session_id) if e["status"] == "complete"]

    def unfinished_experiment(self, session_id: str) -> dict[str, Any] | None:
        for e in self.experiments(session_id):
            if e["status"] not in {"complete", "failed"}:
                return e
        return None

    # ---- events and ARIA messages --------------------------------------------------------
    def log_event(self, session_id: str, kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO events (session_id, ts, kind, message, payload_json) VALUES (?,?,?,?,?)", (session_id, now(), kind, message, json.dumps(payload) if payload else None))

    def events(self, session_id: str, after_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM events WHERE session_id=? AND id>? ORDER BY id LIMIT ?", (session_id, after_id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = _loads(d.pop("payload_json"))
            out.append(d)
        return out

    def record_aria_message(self, session_id: str, *, direction: str, kind: str, artifact_ref: str | None, artifact_digest: str | None, state_revision: int | None, accepted: bool | None, feedback: dict[str, Any] | None, payload: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO aria_messages (session_id, ts, direction, kind, artifact_ref, artifact_digest, state_revision, accepted, feedback_json, payload_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (session_id, now(), direction, kind, artifact_ref, artifact_digest, state_revision, None if accepted is None else int(accepted), json.dumps(feedback) if feedback else None, json.dumps(payload)),
            )

    def aria_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM aria_messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["feedback"] = _loads(d.pop("feedback_json"))
            d["payload"] = _loads(d.pop("payload_json"))
            d["accepted"] = None if d["accepted"] is None else bool(d["accepted"])
            out.append(d)
        return out

    def seen_proposal_ids(self, session_id: str) -> list[str]:
        ids = []
        for m in self.aria_messages(session_id):
            if m["direction"] == "inbound" and m["kind"] == "proposal" and m["accepted"] and isinstance(m["payload"], dict):
                pid = m["payload"].get("proposal_id")
                if pid:
                    ids.append(pid)
        return ids

    def rejection_feedback(self, session_id: str, state_revision: int) -> list[dict[str, Any]]:
        """Structured feedback for rejected inbound messages at the current revision (sent back to ARIA)."""
        out = []
        for m in self.aria_messages(session_id):
            if m["direction"] == "inbound" and m["accepted"] is False and m["state_revision"] == state_revision and m["feedback"]:
                out.append({"artifact": m["artifact_ref"], "feedback": m["feedback"], "ts": m["ts"]})
        return out


# ---- research state rendering ---------------------------------------------------------------

def _compact_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    keep = [
        "score_kind", "benchmark_comparable", "split", "validation_auprc", "validation_auroc", "train_auprc", "threshold_best_f1",
        "confusion_matrix", "false_negative_count", "false_positive_count", "val_positives", "val_size", "train_size", "n_features",
        "feature_importance", "error_breakdowns", "fit_notes", "runtime_seconds", "seed",
    ]
    out = {k: result.get(k) for k in keep if k in result}
    vm = result.get("validation_metrics") or {}
    out["validation_metrics"] = {k: vm[k] for k in ("precision", "recall", "f1", "balanced_accuracy", "brier", "precision_at_5", "recall_at_5", "precision_at_10", "recall_at_10") if k in vm}
    return out


def numeric_best(experiments: list[dict[str, Any]]) -> tuple[str | None, float | None]:
    best_id, best = None, None
    for e in experiments:
        if e["status"] == "complete" and e["score"] is not None and (best is None or e["score"] > best):
            best_id, best = e["id"], float(e["score"])
    return best_id, best


def research_state(store: Store, session_id: str) -> dict[str, Any]:
    """The complete research state sent to ARIA on every cycle and shown in the UI."""
    session = store.get_session(session_id)
    exps = store.experiments(session_id)
    completed = [e for e in exps if e["status"] == "complete"]
    best_id, best = numeric_best(exps)
    baseline = completed[0]["score"] if completed else None
    history = []
    for e in completed:
        history.append(
            {
                "experiment_id": e["id"],
                "iteration": e["iteration"],
                "parent_experiment_id": e["parent_experiment_id"],
                "controller": e["controller"],
                "config_key": e["config_key"],
                "experiment": e["experiment"],
                "change_summary": e["change_summary"],
                "hypothesis": (e["proposal"] or {}).get("hypothesis") if e["proposal"] else "Establish the metadata-only logistic regression baseline (fixed setup, not chosen by ARIA).",
                "observation": (e["proposal"] or {}).get("observation"),
                "expected_result": (e["proposal"] or {}).get("expected_result"),
                "reason": (e["proposal"] or {}).get("reason"),
                "score": e["score"],
                "previous_best": e["previous_best"],
                "delta_vs_previous_best": e["delta"],
                "decision": e["decision"],
                "decision_reason": e["decision_reason"],
                "decision_learning": e["decision_learning"],
                "next_question": e["next_question"],
                "result": _compact_result(e["result"]),
                "runtime_seconds": e["runtime_seconds"],
                "wandb_run_url": e["wandb_run_url"],
                "weave_trace_url": e["weave_trace_url"],
            }
        )
    failed = [
        {"experiment_id": e["id"], "experiment": e["experiment"], "error": e["error"], "hypothesis": (e["proposal"] or {}).get("hypothesis")}
        for e in exps
        if e["status"] == "failed"
    ]
    tested_models = sorted({e["experiment"]["model"] for e in completed})
    tested_protocols = sorted({e["experiment"]["feature_protocol"] for e in completed})
    remaining = max(0, session["budget"] - max(0, len(completed) - 1))  # the baseline does not consume ARIA budget
    pending = None
    unfinished = store.unfinished_experiment(session_id)
    if unfinished:
        pending = {"experiment_id": unfinished["id"], "status": unfinished["status"], "experiment": unfinished["experiment"], "hypothesis": (unfinished["proposal"] or {}).get("hypothesis"), 'observation':(unfinished['proposal'] or {}).get('observation')}
    awaiting_decision_for = completed[-1]["id"] if completed and completed[-1]["decision"] is None else None
    return {
        "schema_version": 1,
        "session_id": session_id,
        "state_revision": session["state_revision"],
        "status": session["status"],
        "aria_mode": session["aria_mode"],
        "generated_at": now(),
        "objective": {
            "metric": "AUPRC (average precision) on the official 2019 validation year",
            "published_benchmark": {"value": protocol.PUBLISHED_TEST_AUPRC, "split": "official 2020 test year, mean over five seeds", "model": protocol.PUBLISHED_MODEL, "comparable_to_validation_scores": False},
            "note": "Validation AUPRC guides selection only. The published 0.533 is a held-out test score; only a frozen final configuration is evaluated on the test year, once, after the loop.",
        },
        "protocol": session["protocol"],
        "capabilities": capability_manifest(),
        "budget": {"max_aria_experiments": session["budget"], "used": max(0, len(completed) - 1), "remaining": remaining, "baseline_counts_toward_budget": False},
        "remaining_budget": remaining,
        "research_seed": session["research_seed"],
        "score_kind_of_history": "VALIDATION_AUPRC unless a row says DEV_SCORE",
        "baseline_validation_auprc": baseline,
        "numeric_best": {"experiment_id": best_id, "validation_auprc": best},
        "current_best_validation_auprc": best,
        "tested_models": tested_models,
        "tested_feature_protocols": tested_protocols,
        "history": history,
        "failed_experiments": failed,
        "pending_experiment": pending,
        "awaiting_decision_for_experiment_id": awaiting_decision_for,
        "seen_proposal_ids": store.seen_proposal_ids(session_id),
        "rejected_messages_at_this_revision": store.rejection_feedback(session_id, session["state_revision"]),
        "final_decision": session["final_decision"],
        "approved_study_plan": _approved_study_context(store, session_id),
        "instructions": _instructions(session, remaining, awaiting_decision_for) + _approved_study_instruction(store, session_id),
    }


def _approved_study_context(store, session_id):
    from .assistant.drafts import approved_context
    return approved_context(store, session_id)


def _approved_study_instruction(store, session_id):
    context = _approved_study_context(store, session_id)
    if not context:
        return ""
    return " Follow approved_study_plan within the capability and budget limits. For an error_proposal plan, the first post-baseline experiment must use its reviewed experiment configuration; independently evaluate the baseline and subsequent results. Do not treat predicted benefits as measurements."


def _instructions(session: dict[str, Any], remaining: int, awaiting_decision_for: str | None) -> str:
    if session["status"] == "awaiting_final_decision" or remaining <= 0:
        return (
            f"Budget exhausted. Publish artifact '{session['id']}-decision-final' (type research-decision, alias latest, file decision.json) "
            f"following capabilities.response_contract.final_decision with state_revision {session['state_revision']}. "
            "Do not propose another training experiment."
        )
    n = session["state_revision"]
    return (
        f"Read this state, then publish ONE proposal artifact named '{session['id']}-proposal-r{n}' (type research-proposal, alias latest, file proposal.json) "
        f"following capabilities.response_contract.proposal with state_revision {n}. "
        + (f"Include previous_decision for experiment {awaiting_decision_for}. " if awaiting_decision_for else "")
        + "Choose one meaningful change grounded in the measured results. Any rejected message feedback is listed in rejected_messages_at_this_revision."
    )
