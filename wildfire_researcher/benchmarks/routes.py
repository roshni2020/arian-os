"""Additive benchmark API; scientific execution delegates to the existing engine."""
from __future__ import annotations

import threading
from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api", tags=["benchmarks"])
_catalog_lock = threading.RLock()
_catalogs: dict[str, Any] = {}


def catalog():
    from .. import api
    from .storage import BenchmarkStore
    from .compatibility import wildfire_benchmark
    path = str(api.store().path)
    with _catalog_lock:
        if path not in _catalogs:
            st = BenchmarkStore(path)
            seed = wildfire_benchmark()
            try:
                st.get(seed["id"])
            except KeyError:
                st.upsert(seed)
            _catalogs[path] = st
        return _catalogs[path]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SyncRequest(Input):
    provider: Literal["huggingface", "openml"] = "huggingface"
    query: str = Field(min_length=1, max_length=200)  # an empty search would return the provider's trending list
    limit: int = Field(default=10, ge=1, le=100)


class ImportRequest(Input):
    url: str = Field(min_length=1, max_length=2048)


class ProjectRequest(Input):
    benchmark_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    experiment_budget: int = Field(default=3, ge=1, le=50)
    overrides: dict[str, Any] = Field(default_factory=dict)
    selected_result_id: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=200)


class StartRequest(Input):
    wait_seconds: int = Field(default=1800, ge=10, le=86400)


class SessionProjectRequest(Input):
    session_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)


def require_get(method, identity):
    try:
        return method(identity)
    except KeyError:
        raise HTTPException(404, "unknown benchmark, import or project") from None


@router.get("/benchmarks")
def benchmarks(q: str = Query("", max_length=200), source: str = "", domain: str = "",
               task_type: str = "", metric: str = "", sort: Literal["readiness", "newest", "smallest", "popular"] = "readiness",
               limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return catalog().list(q=q, source=source, domain=domain, task_type=task_type, metric=metric, sort=sort, limit=limit, offset=offset)


@router.post("/benchmarks/sync")
def sync(req: SyncRequest):
    from .service import sync_provider
    return sync_provider(catalog(), req.provider, req.query, req.limit)


@router.post("/benchmarks/import")
def import_benchmark(req: ImportRequest):
    from .service import import_url
    try:
        return import_url(catalog(), req.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/benchmarks/imports/{identity}")
def get_import(identity: str):
    return require_get(catalog().get_import, identity)


@router.get("/benchmarks/{identity}")
def benchmark(identity: str):
    return require_get(catalog().get, identity)


@router.post("/projects")
def create_project(req: ProjectRequest):
    import json
    if len(json.dumps(req.overrides)) > 32000 or not req.name.strip():
        raise HTTPException(400, "project edits are too large or name is blank")
    st = catalog()
    b = require_get(st.get, req.benchmark_id)
    try:
        return st.create_project(b, req.name.strip(), req.experiment_budget, overrides=req.overrides,
                                 selected_result_id=req.selected_result_id, idempotency_key=req.idempotency_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/projects")
def projects():
    return {"items": catalog().projects()}


@router.post("/projects/from-session")
def project_from_session(req: SessionProjectRequest):
    """Attach existing custom-session identity to the same project model, without execution."""
    from .. import api, config, protocol
    from .compatibility import wildfire_benchmark
    session = require_get(api.store().get_session, req.session_id)
    if not req.name.strip():
        raise HTTPException(400, "project name is blank")
    st = catalog()
    b = wildfire_benchmark()
    actual = {key: session.get(key) for key in ("aria_mode", "fast_mode", "limit_train_samples", "research_seed", "target_metric", "target_value", "wandb_entity", "wandb_project", "protocol")}
    expected = {"aria_mode": "connected", "fast_mode": False, "limit_train_samples": None,
                "research_seed": protocol.RESEARCH_SEED, "target_metric": "test_auprc", "target_value": protocol.PUBLISHED_TEST_AUPRC,
                "wandb_entity": config.WANDB_ENTITY, "wandb_project": config.WANDB_PROJECT, "protocol": protocol.provenance()}
    if actual != expected:
        b["evaluation_protocol"]["session_configuration"] = actual
    try:
        p = st.create_project(b, req.name.strip(), session["budget"], idempotency_key="session:" + req.session_id)
        return st.link_session(p["id"], req.session_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/projects/{identity}")
def project(identity: str):
    return require_get(catalog().get_project, identity)


@router.post("/projects/{identity}/start")
def start_project(identity: str, req: StartRequest | None = None):
    from .. import api, config, protocol
    from ..execution import worker_lease
    from .compatibility import compatibility
    st = catalog()
    with api._lock:
        p = require_get(st.get_project, identity)
        check = compatibility(p["snapshot"])
        if not check["executable"]:
            raise HTTPException(409, "; ".join(check["reasons"]))
        if not protocol.canonical_ready() or protocol.repo_commit() != protocol.PINNED_COMMIT:
            raise HTTPException(409, "pinned WildfireIA code and canonical dataset must be available")
        sid = p.get("session_id")
        if sid:
            session = require_get(api.store().get_session, sid)
            expected = {"aria_mode": "connected", "fast_mode": False, "limit_train_samples": None,
                        "budget": p["experiment_budget"], "research_seed": protocol.RESEARCH_SEED,
                        "target_metric": "test_auprc", "target_value": protocol.PUBLISHED_TEST_AUPRC,
                        "wandb_entity": config.WANDB_ENTITY, "wandb_project": config.WANDB_PROJECT}
            if any(session.get(k) != v for k, v in expected.items()) or session.get("protocol") != protocol.provenance():
                raise HTTPException(409, "linked session does not match the pinned project execution configuration")
            if session["status"] != "created" or api._workers.get(sid) and api._workers[sid].is_alive():
                return {"project": p, "session_id": sid, "journal_url": f"/?session={sid}"}
        if any(w.is_alive() for w in api._workers.values()):
            raise HTTPException(409, "another session worker is active")
        try:
            with worker_lease():
                pass
        except RuntimeError:
            raise HTTPException(409, "another research/evaluation worker is active") from None
        try:
            config.load_wandb_credential()
        except Exception:
            raise HTTPException(409, "W&B credential is required to start real ARIA research") from None
        if not sid:
            # Stable session identity makes recovery after an interrupted start idempotent.
            from datetime import datetime
            sid = "wf-" + datetime.fromisoformat(p["created_at"]).strftime("%Y%m%d-%H%M%S") + "-" + p["id"].replace("-", "")[:4]
            try:
                api.store().get_session(sid)
            except KeyError:
                api.store().create_session(session_id=sid, budget=p["experiment_budget"], aria_mode="connected",
                    research_seed=protocol.RESEARCH_SEED, fast_mode=False, limit_train_samples=None,
                    entity=config.WANDB_ENTITY, project=config.WANDB_PROJECT)
            else:
                # Never adopt an unlinked session, even if a custom caller guessed its ID.
                raise HTTPException(409, "session identity is already occupied; create a new reviewed project")
            st.link_session(identity, sid)
        api._start_worker(sid, (req or StartRequest()).wait_seconds)
        return {"project": st.get_project(identity), "session_id": sid, "journal_url": f"/?session={sid}"}
