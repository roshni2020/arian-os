"""DEVELOPMENT-ONLY fallback researcher (ARIA_MODE=fallback).

This is a deterministic scripted stub used to exercise the loop, persistence and UI without
network access. It is NOT a research agent, it is never used when ARIA_MODE=connected, and
every session it drives is labelled aria_mode=fallback in the database, W&B config and UI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCRIPT = [
    {"model": "logistic_regression", "feature_protocol": "metadata_fuel", "weather_days": 5, "hyperparameters": {}},
    {"model": "xgboost", "feature_protocol": "metadata_fuel", "weather_days": 5, "hyperparameters": {}},
    {"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {}},
    {"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {"max_depth": 6}},
]


class FallbackARIA:
    def __init__(self, session_id: str, download_root: Path):
        self.session_id = session_id
        self.download_root = Path(download_root)
        self.state: dict[str, Any] | None = None

    def publish_state_local(self, state: dict[str, Any]) -> None:
        self.state = state

    def wait_for(self, kind: str, revision: int, **_kwargs) -> tuple[dict[str, Any], dict[str, Any]]:
        state = self.state
        if state is None or state["state_revision"] != revision:
            raise RuntimeError("fallback stub has no state for this revision")
        history = state["history"]
        last = history[-1]
        best = state["numeric_best"]["validation_auprc"]
        decision = {
            "experiment_id": last["experiment_id"],
            "decision": "KEEP" if last["score"] is not None and best is not None and last["score"] >= best else "REJECT",
            "reason": f"[FALLBACK STUB] {last['experiment_id']} scored {last['score']:.4f}; numeric best is {best:.4f}.",
            "learning": "[FALLBACK STUB] scripted development decision, not research reasoning.",
            "next_question": "[FALLBACK STUB] next scripted configuration.",
        }
        path = self.download_root / f"fallback-r{revision}-{kind}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "decision":
            payload = {"schema_version": 1, "session_id": self.session_id, "state_revision": revision, **decision, "recommended_final_experiment_id": state["numeric_best"]["experiment_id"]}
        else:
            tried = {json.dumps(h["experiment"], sort_keys=True) for h in history}
            nxt = next((c for c in SCRIPT if json.dumps(_fill(c), sort_keys=True) not in tried), None)
            if nxt is None:
                raise RuntimeError("fallback script exhausted")
            payload = {
                "schema_version": 1,
                "session_id": self.session_id,
                "state_revision": revision,
                "proposal_id": f"fallback-r{revision}",
                "observation": f"[FALLBACK STUB] last validation AUPRC {last['score']:.4f}, {last['result']['false_negative_count']} false negatives.",
                "hypothesis": "[FALLBACK STUB] scripted next configuration for development testing only.",
                "expected_result": "[FALLBACK STUB] unknown.",
                "reason": "[FALLBACK STUB] not a research decision.",
                "experiment": nxt,
                "previous_decision": decision,
            }
        path.write_text(json.dumps(payload, indent=2))
        meta = {"artifact_ref": f"local://fallback/{path.name}", "artifact_version": "v0", "artifact_digest": None, "file_sha256": None, "artifact_metadata": {"aria_mode": "fallback"}, "local_path": str(path)}
        return payload, meta


def _fill(c: dict[str, Any]) -> dict[str, Any]:
    from .experiments import canonical_experiment

    return canonical_experiment(c)
