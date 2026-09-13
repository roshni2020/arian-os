"""W&B Models + Weave wrappers.

Design rules:
- Every experiment is a W&B run with session/iteration/parent identity, config, metrics, deltas and provenance.
- Weave ops trace what actually happens locally: receipt of ARIA outputs, validation, training,
  evaluation, decision recording and state publication. ARIA's internal reasoning is NOT
  instrumented here; ARIA runs in W&B's own environment and each event is a fresh conversation.
  We never fabricate spans for it.
- Upload failures raise; they are never swallowed into a fake success.
- The API key is read from the environment only and never logged.
"""
from __future__ import annotations

import hashlib
import json
import functools
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from . import config

_weave_client = None
_weave = None
_wandb = None


def _ensure_imports():
    global _weave, _wandb
    if _wandb is None:
        config.load_wandb_credential()
        import wandb  # noqa: WPS433
        import weave  # noqa: WPS433

        _wandb = wandb
        _weave = weave
    return _wandb, _weave


def init_weave(entity: str, project: str):
    """Initialise Weave once per process. Returns the client."""
    global _weave_client
    wandb, weave = _ensure_imports()
    if _weave_client is None:
        _weave_client = weave.init(f"{entity}/{project}")
    return _weave_client


def op(name: str) -> Callable:
    """Decorator that traces a function with Weave when available, otherwise no-op."""

    def wrap(fn: Callable) -> Callable:
        traced = None
        @functools.wraps(fn)
        def invoke(*args, **kwargs):
            nonlocal traced
            enabled = getattr(args[0], 'tracking_enabled', _weave_client is not None) if args else _weave_client is not None
            if not enabled:
                return fn(*args, **kwargs)
            if traced is None:
                _, weave = _ensure_imports()
                traced = weave.op(name=name)(fn)
            return traced(*args, **kwargs)
        return invoke

    return wrap


@contextmanager
def research_context(entity, project, session_id, run_id, revision):
    client = init_weave(entity, project)
    if run_id:
        client.set_wandb_run_context(run_id=run_id)
    try:
        with _weave.attributes({'research_session_id':session_id,'state_revision':revision,
                                'stage':'external_aria_exchange'}):
            yield
    finally:
        client.clear_wandb_run_context()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sanitize_for_log(payload: dict[str, Any]) -> dict[str, Any]:
    """Defensive: never let anything key-like reach run metadata."""
    banned = {"WANDB_API_KEY", "api_key", "apikey", "token", "secret", "password"}
    out = {}
    for k, v in payload.items():
        if k in banned or any(b.lower() in str(k).lower() for b in ("api_key", "secret", "token", "password")):
            continue
        out[k] = v
    return out


class ExperimentRun:
    """Context manager around one W&B run for one experiment."""

    def __init__(self, *, entity: str, project: str, session_id: str, experiment_id: str, iteration: int, run_kind: str, exp_config: dict[str, Any], group: str | None = None, tags: list[str] | None = None):
        self.entity, self.project = entity, project
        self.session_id, self.experiment_id, self.iteration = session_id, experiment_id, iteration
        self.run_kind = run_kind
        self.exp_config = sanitize_for_log(exp_config)
        self.group = group or session_id
        self.tags = tags or []
        self.run = None
        self.url: str | None = None
        self.id: str | None = None

    def __enter__(self) -> "ExperimentRun":
        wandb, _ = _ensure_imports()
        name = f"{self.session_id}-{self.experiment_id}" if self.run_kind == "experiment" else f"{self.session_id}-{self.run_kind}"
        self.run = wandb.init(
            entity=self.entity,
            project=self.project,
            group=self.group,
            name=name,
            job_type=self.run_kind,
            tags=self.tags,
            config={"session_id": self.session_id, "experiment_id": self.experiment_id, "iteration": self.iteration, **self.exp_config},
            reinit="finish_previous",
        )
        self.url = self.run.url
        self.id = self.run.id
        try:
            client = init_weave(self.entity, self.project)
            client.set_wandb_run_context(run_id=self.run.id)
        except Exception:
            self.run.finish(exit_code=1)
            raise
        return self

    def log(self, metrics: dict[str, Any]) -> None:
        self.run.log({k: v for k, v in metrics.items() if isinstance(v, (int, float)) and not isinstance(v, bool)})

    def summary(self, fields: dict[str, Any]) -> None:
        for k, v in fields.items():
            self.run.summary[k] = v

    def log_table(self, name: str, columns: list[str], rows: list[list[Any]]) -> None:
        wandb, _ = _ensure_imports()
        self.run.log({name: wandb.Table(columns=columns, data=rows)})

    def log_pr_curve(self, curve: list[dict[str, float]]) -> None:
        self.log_table("pr_curve", ["recall", "precision"], [[p["recall"], p["precision"]] for p in curve])

    def log_artifact(self, name: str, kind: str, files: dict[str, Path], metadata: dict[str, Any] | None = None, aliases: list[str] | None = None):
        wandb, _ = _ensure_imports()
        art = wandb.Artifact(name, type=kind, metadata=sanitize_for_log(metadata or {}))
        for arcname, path in files.items():
            art.add_file(str(path), name=arcname)
        logged = self.run.log_artifact(art, aliases=aliases or ["latest"])
        logged.wait()
        return logged

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if _weave_client is not None:
                _weave_client.clear_wandb_run_context()
        except Exception:
            pass
        if self.run is not None:
            self.run.finish(exit_code=0 if exc is None else 1)


def latest_trace_url(entity: str, project: str, run_id: str | None) -> str | None:
    """Best-effort link to the Weave traces filtered to this run."""
    base = f"https://wandb.ai/{entity}/{project}/weave/traces"
    return f"{base}?filter=wb_run_id%3D{run_id}" if run_id else base


def experiment_config_payload(session: dict[str, Any], experiment: dict[str, Any], exp: dict[str, Any], previous_best: float | None) -> dict[str, Any]:
    proposal = experiment.get("proposal") or {}
    return {
        "controller": "ARIA" if proposal else "baseline_setup",
        "parent_experiment_id": experiment.get("parent_experiment_id"),
        "model": exp["model"],
        "feature_protocol": exp["feature_protocol"],
        "weather_days": exp["weather_days"],
        "hyperparameters": exp["hyperparameters"],
        "hypothesis": proposal.get("hypothesis"),
        "observation": proposal.get("observation"),
        "expected_result": proposal.get("expected_result"),
        "reason": proposal.get("reason"),
        "change_summary": experiment.get("change_summary"),
        "previous_best_validation_auprc": previous_best,
        "target_test_auprc": config.TARGET_AUPRC,
        "score_kind": "VALIDATION_AUPRC",
        "benchmark_comparable": False,
        "research_seed": session["research_seed"],
        "aria_mode": session["aria_mode"],
        "protocol": session["protocol"],
        "proposal_source": experiment.get("proposal_source"),
    }


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(path)
    return path
