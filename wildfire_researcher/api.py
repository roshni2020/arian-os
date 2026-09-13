"""FastAPI backend: sessions, live status, experiment details, replay, control.

The research loop runs in a background thread of this process (one worker per session).
All numbers come from the SQLite store; the frontend never computes scientific claims.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config, protocol
from .state import Store, research_state

app = FastAPI(title="ARIA Wildfire Researcher", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_store: Store | None = None
_workers: dict[str, threading.Thread] = {}
_lock = threading.RLock()


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


class StartRequest(BaseModel):
    budget: int = Field(default=config.DEFAULT_BUDGET, ge=1, le=50)
    aria_mode: str = Field(default=config.ARIA_MODE, pattern="^(connected|fallback)$")
    session_id: str | None = None
    limit_train_samples: int | None = Field(default=None, ge=200)
    wait_seconds: int = Field(default=config.ARIA_WAIT_SECONDS, ge=10, le=86400)


def _start_worker(session_id: str, wait_seconds: int) -> None:
    from .loop import ResearchLoop, make_aria

    with _lock:
        if any(w.is_alive() for w in _workers.values()):
            raise HTTPException(409, "another session worker is active; local execution is serialized")
        st = store()
        session = st.get_session(session_id)
        tracking_enabled = session["aria_mode"] == "connected"
        if tracking_enabled:
            config.load_wandb_credential()
        aria = make_aria(session, config.ARTIFACTS_DIR / session_id / "aria")

        def target():
            loop = ResearchLoop(st, session_id, aria, tracking_enabled=tracking_enabled, wait_seconds=wait_seconds, log=lambda m: None)
            try:
                loop.run()
            except Exception as exc:
                st.update_session(session_id, error=str(exc))
                st.set_status(session_id, 'error', str(exc))

        t = threading.Thread(target=target, name=f"worker-{session_id}", daemon=True)
        _workers[session_id] = t
        t.start()


def _session_view(session_id: str) -> dict[str, Any]:
    st = store()
    session = st.get_session(session_id)
    from .final_eval import evaluation_view
    session['final_evaluation'] = evaluation_view(session['final_evaluation'])
    state = research_state(st, session_id)
    worker = _workers.get(session_id)
    experiments = st.experiments(session_id)
    return {
        "session": session,
        "state": state,
        "experiments": [{k: v for k, v in e.items() if k != "result"} | {"result": _compact(e["result"])} for e in experiments],
        "worker_alive": bool(worker and worker.is_alive()),
        "mode_label": _mode_label(session, worker),
        "benchmark": {"published_test_auprc": protocol.PUBLISHED_TEST_AUPRC, "published_model": protocol.PUBLISHED_MODEL, "beaten": bool((session.get("final_evaluation") or {}).get("benchmark_beaten"))},
        "dataset": _dataset_context(),
    }


def _compact(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {k: v for k, v in result.items() if k not in {"pr_curve"}}


ACTIVE_STATUSES = {"running_baseline", "awaiting_aria_proposal", "validating_proposal", "training", "evaluating", "awaiting_final_decision", "final_evaluation"}


def _mode_label(session: dict[str, Any], worker) -> str:
    if session["aria_mode"] == "replay":
        return "REPLAYING VERIFIED RUN"
    if session["aria_mode"] == "fallback":
        return "DEVELOPMENT FALLBACK (NOT ARIA)"
    if (worker and worker.is_alive()) or session["status"] in ACTIVE_STATUSES:
        return "LIVE RUN"  # a worker in this process or the CLI worker is driving the session
    return "RECORDED RUN"


def _dataset_context() -> dict[str, Any]:
    ctx = {
        "events_total": 38128,
        "task_events": {"train_2016_2018": 22576, "val_2019": 7047, "test_2020": 6168},
        "positives": {"train": 1704, "val": 428, "test": 513},
        "inputs": ["FPA-FOD incident metadata", "FIRMS/VIIRS discovery-day thermal detections", "gridMET weather + fire danger (D-4..D)", "LANDFIRE fuel + vegetation", "topography", "OpenStreetMap access", "WorldPop population"],
        "prediction": "Will initial attack fail? (final size >= 50 ha vs <= 10 ha; 10-50 ha excluded)",
        "constraint": protocol.PREDICTION_TIME,
        "forbidden": protocol.forbidden_columns() if protocol.canonical_ready() else [],
        "provenance": protocol.provenance(),
        "canonical_ready": protocol.canonical_ready(),
    }
    return ctx


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "aria_mode_default": config.ARIA_MODE, "fast_mode": config.FAST_MODE, "canonical_ready": protocol.canonical_ready(), "wandb_project": f"{config.WANDB_ENTITY}/{config.WANDB_PROJECT}", "credential_present": config.credential_present() or _credential_available()}


def _credential_available() -> bool:
    try:
        config.load_wandb_credential()
        return True
    except Exception:
        return False


@app.get("/api/sessions")
def sessions() -> list[dict[str, Any]]:
    from .final_eval import evaluation_view
    out = []
    for s in store().list_sessions():
        s['final_evaluation'] = evaluation_view(s['final_evaluation'])
        worker = _workers.get(s["id"])
        out.append({"id": s["id"], "status": s["status"], "aria_mode": s["aria_mode"], "created_at": s["created_at"], "current_best_auprc": s["current_best_auprc"], "budget": s["budget"], "worker_alive": bool(worker and worker.is_alive()), "mode_label": _mode_label(s, worker), "benchmark_beaten": bool((s.get("final_evaluation") or {}).get("benchmark_beaten"))})
    return out


@app.post("/api/sessions")
def start_session(req: StartRequest) -> dict[str, Any]:
    if not protocol.canonical_ready():
        raise HTTPException(400, "WildfireIA canonical tables are not set up; run `python -m wildfire_researcher.cli setup-data`")
    if req.aria_mode == "connected":
        try:
            config.load_wandb_credential()
        except Exception as exc:
            raise HTTPException(400, str(exc))
    with _lock:
        if any(w.is_alive() for w in _workers.values()):
            raise HTTPException(409, 'another session worker is active')
        session = store().create_session(session_id=req.session_id, budget=req.budget, aria_mode=req.aria_mode, research_seed=protocol.RESEARCH_SEED, fast_mode=config.FAST_MODE, limit_train_samples=req.limit_train_samples, entity=config.WANDB_ENTITY, project=config.WANDB_PROJECT)
        _start_worker(session["id"], req.wait_seconds)
    return _session_view(session["id"])


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    try:
        return _session_view(session_id)
    except KeyError:
        raise HTTPException(404, "unknown session")


@app.get("/api/sessions/{session_id}/events")
def events(session_id: str, after: int = 0) -> list[dict[str, Any]]:
    return store().events(session_id, after_id=after)


@app.get("/api/sessions/{session_id}/execution-status")
def get_execution_status(session_id: str) -> dict[str, Any]:
    from .execution_status import ExecutionStatusUnavailable, execution_status
    try:
        return execution_status(store(), session_id, local_worker=_workers.get(session_id),
                                operations_dir=config.ARTIFACTS_DIR / "operations")
    except KeyError:
        raise HTTPException(404, "unknown session") from None
    except ExecutionStatusUnavailable as exc:
        raise HTTPException(503, str(exc)) from None


@app.get("/api/sessions/{session_id}/experiments/{experiment_id}")
def experiment(session_id: str, experiment_id: str) -> dict[str, Any]:
    try:
        e = store().get_experiment(session_id, experiment_id)
    except KeyError:
        raise HTTPException(404, "unknown experiment")
    return e


@app.get("/api/sessions/{session_id}/aria-messages")
def aria_messages(session_id: str) -> list[dict[str, Any]]:
    return store().aria_messages(session_id)


@app.post("/api/sessions/{session_id}/cancel")
def cancel(session_id: str) -> dict[str, Any]:
    st = store()
    st.update_session(session_id, cancel_requested=True)
    st.log_event(session_id, "cancel_requested", "Cancellation requested from UI")
    return {"ok": True}


class ResumeRequest(BaseModel):
    wait_seconds: int = Field(default=config.ARIA_WAIT_SECONDS, ge=10, le=86400)


@app.post("/api/sessions/{session_id}/resume")
def resume(session_id: str, req: ResumeRequest | None = None) -> dict[str, Any]:
    st = store()
    session = st.get_session(session_id)
    if session.get('protocol',{}).get('execution_backend') == 'wandb-launch':
        raise HTTPException(409, 'This session is controlled through W&B Launch. Inspect its queued job and continue through ARIA; the local artifact worker cannot resume it.')
    if session["status"] in {"complete"}:
        raise HTTPException(400, "session is complete")
    st.update_session(session_id, cancel_requested=False, error=None)
    _start_worker(session_id, (req or ResumeRequest()).wait_seconds)
    return _session_view(session_id)


@app.get("/api/sessions/{session_id}/replay")
def replay(session_id: str) -> dict[str, Any]:
    """Verified record for replay: stored results only, no retraining, no ARIA calls."""
    from .loop import replay_record

    try:
        return replay_record(store(), session_id)
    except KeyError:
        raise HTTPException(404, "unknown session")


@app.get("/api/replays")
def replays() -> list[dict[str, Any]]:
    """Replay files exported under artifacts/<session>/replay.json (survive database resets)."""
    out = []
    if config.ARTIFACTS_DIR.exists():
        for path in sorted(config.ARTIFACTS_DIR.glob("*/replay.json")):
            try:
                rec = json.loads(path.read_text())
                s = rec["session"]
                out.append({"id": s["id"], "status": s["status"], "aria_mode": s["aria_mode"], "current_best_auprc": s["current_best_auprc"], "experiments": len(rec["experiments"]), "path": str(path)})
            except Exception:
                continue
    return out


@app.get("/api/replays/{session_id}")
def replay_file(session_id: str) -> dict[str, Any]:
    path = config.ARTIFACTS_DIR / session_id / "replay.json"
    if not path.exists():
        raise HTTPException(404, "no replay file")
    return json.loads(path.read_text())


@app.get("/api/automation-prompt/{session_id}")
def automation_prompt(session_id: str, generic: bool = True) -> dict[str, Any]:
    from .aria_client import automation_prompt as build

    session = store().get_session(session_id)
    prompt = build(None if generic else session_id, session["wandb_entity"], session["wandb_project"])
    from .aria_client import GENERIC_RUN_NAME_REGEX

    regex = GENERIC_RUN_NAME_REGEX if generic else f"^{session_id}-(exp-\\d+|control-r\\d+)$"
    return {"prompt": prompt, "chars": len(prompt), "run_name_regex": regex, "generic": generic, "event": "run status changed -> finished", "project": session["wandb_project"]}


# Discovery/import is additive and delegates supported execution to the existing worker.
from .benchmarks.routes import router as benchmark_router
app.include_router(benchmark_router)
