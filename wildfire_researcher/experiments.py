"""Strict, typed experiment contract between ARIA and the executor.

ARIA output is data. It is parsed against a closed schema with bounded values; nothing in a
proposal is ever executed, interpolated into a shell, or used as a path.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from . import protocol

SCHEMA_VERSION = 1
MAX_TEXT = 4000

MODELS: dict[str, dict[str, Any]] = {
    "logistic_regression": {
        "description": "sklearn LogisticRegression (lbfgs, max_iter=5000) on standardized official tabular cache. Official baseline uses C=1.0, class_weight=balanced.",
        "hyperparameters": {
            "C": {"type": "float", "min": 0.01, "max": 10.0, "default": 1.0},
            "class_weight": {"type": "enum", "values": ["balanced", None], "default": "balanced"},
        },
        "typical_runtime_seconds": {"metadata": 20, "all": 300},
    },
    "xgboost": {
        "description": "XGBClassifier (hist, eval_metric=aucpr, early_stopping_rounds=50 on validation as in the official script). Official config: n_estimators=1000, learning_rate=0.03, max_depth=4, subsample=0.8, colsample_bytree=0.8, scale_pos_weight=neg/pos.",
        "hyperparameters": {
            "n_estimators": {"type": "int", "min": 50, "max": 2000, "default": 1000},
            "learning_rate": {"type": "float", "min": 0.005, "max": 0.3, "default": 0.03},
            "max_depth": {"type": "int", "min": 2, "max": 10, "default": 4},
            "subsample": {"type": "float", "min": 0.5, "max": 1.0, "default": 0.8},
            "colsample_bytree": {"type": "float", "min": 0.2, "max": 1.0, "default": 0.8},
            "min_child_weight": {"type": "float", "min": 1.0, "max": 50.0, "default": 1.0},
            "reg_lambda": {"type": "float", "min": 0.0, "max": 20.0, "default": 1.0},
            "reg_alpha": {"type": "float", "min": 0.0, "max": 20.0, "default": 0.0},
            "gamma": {"type": "float", "min": 0.0, "max": 10.0, "default": 0.0},
            "scale_pos_weight": {"type": "float_or_auto", "min": 0.5, "max": 50.0, "default": "auto"},
        },
        "typical_runtime_seconds": {"metadata": 60, "all": 400},
    },
}

BASELINE_EXPERIMENT = {
    "model": "logistic_regression",
    "feature_protocol": "metadata",
    "weather_days": 5,
    "hyperparameters": {"C": 1.0, "class_weight": "balanced"},
}


class ProposalError(ValueError):
    """Raised when an ARIA proposal fails validation. `feedback` is structured and safe to send back."""

    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.field = field
        self.message = message

    def feedback(self) -> dict[str, Any]:
        return {"code": self.code, "field": self.field, "message": self.message}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (_is_int(value) or isinstance(value, float)) and math.isfinite(value)


def _text(proposal: dict, key: str, required: bool = True) -> str:
    value = proposal.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise ProposalError("missing_text", f"'{key}' must be nonempty text", key)
    if len(value) > MAX_TEXT:
        raise ProposalError("text_too_long", f"'{key}' exceeds {MAX_TEXT} characters", key)
    return value.strip()


def capability_manifest() -> dict[str, Any]:
    """What ARIA may choose from. Sent with every research state."""
    return {
        "schema_version": SCHEMA_VERSION,
        "representation": "tabular",
        "models": {name: {"description": spec["description"], "hyperparameters": spec["hyperparameters"]} for name, spec in MODELS.items()},
        "feature_protocols": {p: protocol.PROTOCOL_DESCRIPTIONS[p] for p in protocol.FEATURE_PROTOCOLS},
        "weather_days": protocol.WEATHER_DAYS,
        "weather_days_note": "Only affects protocols that include weather; otherwise it is canonicalized to 5.",
        "rules": [
            "Exactly one model, one feature_protocol, one weather_days and a hyperparameters object; no other keys.",
            "Prefer one meaningful change per experiment; explain any multi-variable change in 'reason'.",
            "Identical canonical configurations are rejected as duplicates.",
            "The optimization objective is validation AUPRC (official metric on the official 2019 validation year).",
            "Test-year (2020) results are sealed until a final configuration is frozen; they are never shown to ARIA.",
            "Forbidden leakage columns (final size, containment time, MTBS ids) are removed by the official dataloader and cannot be requested.",
            "'firms' restricts the sample to events with VIIRS matches, so its scores are not comparable with other protocols.",
        ],
        "response_contract": {
            "proposal": {
                "schema_version": SCHEMA_VERSION,
                "session_id": "<from state>",
                "state_revision": "<from state>",
                "proposal_id": "<unique string>",
                "observation": "text grounded in the measured results in the state",
                "hypothesis": "one falsifiable expected improvement",
                "expected_result": "text",
                "reason": "text",
                "experiment": {"model": "xgboost", "feature_protocol": "metadata_fuel", "weather_days": 5, "hyperparameters": {}},
                "previous_decision": {"experiment_id": "<id of the last experiment>", "decision": "KEEP|REJECT", "reason": "text", "learning": "text", "next_question": "text"},
            },
            "final_decision": {
                "schema_version": SCHEMA_VERSION,
                "session_id": "<from state>",
                "state_revision": "<from state>",
                "experiment_id": "<id of the last experiment>",
                "decision": "KEEP|REJECT",
                "reason": "text",
                "learning": "text",
                "next_question": "text",
                "recommended_final_experiment_id": "<experiment id to freeze for official test evaluation>",
            },
        },
    }


def canonical_experiment(exp: Any) -> dict[str, Any]:
    """Validate the experiment block and return a fully specified canonical configuration."""
    if not isinstance(exp, dict):
        raise ProposalError("bad_experiment", "'experiment' must be an object", "experiment")
    allowed_keys = {"model", "feature_protocol", "weather_days", "hyperparameters"}
    extra = set(exp) - allowed_keys
    if extra:
        raise ProposalError("unknown_keys", f"experiment has unsupported keys: {sorted(extra)}", "experiment")
    missing = allowed_keys - set(exp)
    if missing:
        raise ProposalError("missing_keys", f"experiment is missing keys: {sorted(missing)}", "experiment")
    model = exp["model"]
    if model not in MODELS:
        raise ProposalError("bad_model", f"model must be one of {sorted(MODELS)}", "experiment.model")
    fp = exp["feature_protocol"]
    if fp not in protocol.FEATURE_PROTOCOLS:
        raise ProposalError("bad_protocol", f"feature_protocol must be one of {protocol.FEATURE_PROTOCOLS}", "experiment.feature_protocol")
    wd = exp["weather_days"]
    if not _is_int(wd) or wd not in protocol.WEATHER_DAYS:
        raise ProposalError("bad_weather_days", f"weather_days must be an integer in {protocol.WEATHER_DAYS}", "experiment.weather_days")
    if not protocol.protocol_includes_weather(fp):
        wd = 5  # irrelevant for this protocol; canonicalize so duplicates are detected
    hp_in = exp["hyperparameters"]
    if not isinstance(hp_in, dict):
        raise ProposalError("bad_hyperparameters", "'hyperparameters' must be an object", "experiment.hyperparameters")
    spec = MODELS[model]["hyperparameters"]
    extra = set(hp_in) - set(spec)
    if extra:
        raise ProposalError("unknown_hyperparameters", f"{model} does not accept hyperparameters {sorted(extra)}", "experiment.hyperparameters")
    hp: dict[str, Any] = {}
    for name, rule in spec.items():
        value = hp_in.get(name, rule["default"])
        field = f"experiment.hyperparameters.{name}"
        kind = rule["type"]
        if kind == "enum":
            if value not in rule["values"]:
                raise ProposalError("bad_value", f"{name} must be one of {rule['values']}", field)
            hp[name] = value
        elif kind == "int":
            if not _is_int(value) or not rule["min"] <= value <= rule["max"]:
                raise ProposalError("bad_value", f"{name} must be an integer in [{rule['min']}, {rule['max']}]", field)
            hp[name] = int(value)
        elif kind == "float":
            if not _is_number(value) or not rule["min"] <= value <= rule["max"]:
                raise ProposalError("bad_value", f"{name} must be a finite number in [{rule['min']}, {rule['max']}]", field)
            hp[name] = float(value)
        elif kind == "float_or_auto":
            if value == "auto":
                hp[name] = "auto"
            elif _is_number(value) and rule["min"] <= value <= rule["max"]:
                hp[name] = float(value)
            else:
                raise ProposalError("bad_value", f"{name} must be 'auto' or a finite number in [{rule['min']}, {rule['max']}]", field)
        else:  # pragma: no cover
            raise ProposalError("internal", f"unknown rule type {kind}", field)
    return {"model": model, "feature_protocol": fp, "weather_days": int(wd), "hyperparameters": dict(sorted(hp.items()))}


def config_key(experiment: dict[str, Any], seed: int, representation: str = "tabular") -> str:
    payload = json.dumps({"experiment": experiment, "seed": seed, "representation": representation, "task": protocol.TASK}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def describe_change(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    """Human-readable diff between two canonical experiments (used in run names and UI)."""
    if previous is None:
        return ["baseline"]
    changes = []
    if previous["model"] != current["model"]:
        changes.append(f"model {previous['model']} -> {current['model']}")
    if previous["feature_protocol"] != current["feature_protocol"]:
        changes.append(f"features {previous['feature_protocol']} -> {current['feature_protocol']}")
    if previous["weather_days"] != current["weather_days"]:
        changes.append(f"weather_days {previous['weather_days']} -> {current['weather_days']}")
    if previous["model"] == current["model"]:
        for k, v in current["hyperparameters"].items():
            if previous["hyperparameters"].get(k) != v:
                changes.append(f"{k} {previous['hyperparameters'].get(k)} -> {v}")
    return changes or ["no change"]


def _decision_block(block: Any, field: str, require_experiment_id: bool) -> dict[str, Any]:
    if not isinstance(block, dict):
        raise ProposalError("bad_decision", f"'{field}' must be an object", field)
    if block.get("decision") not in ("KEEP", "REJECT"):
        raise ProposalError("bad_decision", f"'{field}.decision' must be KEEP or REJECT", f"{field}.decision")
    out = {"decision": block["decision"]}
    for key in ("reason", "learning"):
        out[key] = _text(block, key)
    out["next_question"] = _text(block, "next_question", required=False)
    exp_id = block.get("experiment_id")
    if require_experiment_id and (not isinstance(exp_id, str) or not exp_id.strip()):
        raise ProposalError("bad_decision", f"'{field}.experiment_id' is required", f"{field}.experiment_id")
    out["experiment_id"] = exp_id.strip() if isinstance(exp_id, str) else None
    return out


def validate_proposal(proposal: Any, state: dict[str, Any]) -> dict[str, Any]:
    """Validate an ARIA proposal against the current research state.

    Returns {"experiment": canonical, "previous_decision": {...}, "proposal_id", "observation", ...}.
    """
    if not isinstance(proposal, dict):
        raise ProposalError("bad_proposal", "proposal must be a JSON object")
    required = {"schema_version", "session_id", "state_revision", "proposal_id", "observation", "hypothesis", "expected_result", "reason", "experiment", "previous_decision"}
    missing = required - set(proposal)
    if missing:
        raise ProposalError("missing_fields", f"proposal is missing fields: {sorted(missing)}")
    extra = set(proposal) - required
    if extra:
        raise ProposalError("unknown_fields", f"proposal has unsupported fields: {sorted(extra)}")
    if proposal["schema_version"] != SCHEMA_VERSION:
        raise ProposalError("bad_schema_version", f"schema_version must be {SCHEMA_VERSION}", "schema_version")
    if proposal["session_id"] != state["session_id"]:
        raise ProposalError("wrong_session", f"proposal is for session {proposal['session_id']!r}, current session is {state['session_id']!r}", "session_id")
    if not _is_int(proposal["state_revision"]) or proposal["state_revision"] != state["state_revision"]:
        raise ProposalError("stale_revision", f"proposal targets state_revision {proposal['state_revision']!r}; current revision is {state['state_revision']}", "state_revision")
    proposal_id = _text(proposal, "proposal_id")
    if len(proposal_id) > 200:
        raise ProposalError("bad_proposal_id", "proposal_id is too long", "proposal_id")
    if proposal_id in {p for p in state.get("seen_proposal_ids", [])}:
        raise ProposalError("duplicate_proposal_id", f"proposal_id {proposal_id!r} was already processed", "proposal_id")
    text = {k: _text(proposal, k) for k in ("observation", "hypothesis", "expected_result", "reason")}
    experiment = canonical_experiment(proposal["experiment"])
    seed = state.get("research_seed", protocol.RESEARCH_SEED)
    key = config_key(experiment, seed)
    for row in state.get("history", []):
        if row.get("config_key") == key:
            raise ProposalError("duplicate_experiment", f"this exact configuration was already run as experiment {row['experiment_id']}", "experiment")
    history = state.get("history", [])
    decision = _decision_block(proposal["previous_decision"], "previous_decision", require_experiment_id=bool(history))
    if history:
        last_id = history[-1]["experiment_id"]
        if decision["experiment_id"] != last_id:
            raise ProposalError("wrong_decision_target", f"previous_decision.experiment_id must be {last_id!r} (the last completed experiment)", "previous_decision.experiment_id")
    if state.get("remaining_budget", 0) <= 0:
        raise ProposalError("budget_exhausted", "experiment budget is exhausted; a final decision is required instead of a proposal")
    return {"proposal_id": proposal_id, **text, "experiment": experiment, "config_key": key, "previous_decision": decision}


def validate_final_decision(decision: Any, state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(decision, dict):
        raise ProposalError("bad_decision", "final decision must be a JSON object")
    required = {"schema_version", "session_id", "state_revision", "experiment_id", "decision", "reason", "learning", "next_question", "recommended_final_experiment_id"}
    missing = required - set(decision)
    if missing:
        raise ProposalError("missing_fields", f"final decision is missing fields: {sorted(missing)}")
    extra = set(decision) - required
    if extra:
        raise ProposalError("unknown_fields", f"final decision has unsupported fields: {sorted(extra)}")
    if decision["schema_version"] != SCHEMA_VERSION:
        raise ProposalError("bad_schema_version", f"schema_version must be {SCHEMA_VERSION}", "schema_version")
    if decision["session_id"] != state["session_id"]:
        raise ProposalError("wrong_session", "final decision is for a different session", "session_id")
    if not _is_int(decision["state_revision"]) or decision["state_revision"] != state["state_revision"]:
        raise ProposalError("stale_revision", f"final decision targets revision {decision['state_revision']!r}; current is {state['state_revision']}", "state_revision")
    block = _decision_block(decision, "final_decision", require_experiment_id=True)
    history = state.get("history", [])
    ids = {row["experiment_id"] for row in history}
    if history and block["experiment_id"] != history[-1]["experiment_id"]:
        raise ProposalError("wrong_decision_target", f"experiment_id must be {history[-1]['experiment_id']!r}", "experiment_id")
    rec = decision["recommended_final_experiment_id"]
    if not isinstance(rec, str) or rec not in ids:
        raise ProposalError("bad_recommendation", f"recommended_final_experiment_id must be one of the completed experiments {sorted(ids)}", "recommended_final_experiment_id")
    block["recommended_final_experiment_id"] = rec
    return block
