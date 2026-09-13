"""Strict proposal parsing, canonicalization and deduplication (no network, no training)."""
from __future__ import annotations

import copy
import math

import pytest

from wildfire_researcher import experiments as ex
from wildfire_researcher import protocol


def _state(history=None, revision=3, budget=5):
    return {
        "session_id": "wf-test",
        "state_revision": revision,
        "research_seed": protocol.RESEARCH_SEED,
        "history": history or [],
        "remaining_budget": budget,
        "seen_proposal_ids": [],
    }


def _proposal(**over):
    p = {
        "schema_version": 1,
        "session_id": "wf-test",
        "state_revision": 3,
        "proposal_id": "p-1",
        "observation": "Baseline misses most positives.",
        "hypothesis": "Fuel adds signal.",
        "expected_result": "Higher validation AUPRC.",
        "reason": "Fuel is the strongest omitted static source.",
        "experiment": {"model": "logistic_regression", "feature_protocol": "metadata_fuel", "weather_days": 5, "hyperparameters": {"C": 1.0, "class_weight": "balanced"}},
        "previous_decision": {"experiment_id": "exp-000", "decision": "REJECT", "reason": "Weak.", "learning": "Metadata insufficient.", "next_question": "Does fuel help?"},
    }
    p.update(over)
    return p


def test_valid_proposal_canonicalizes():
    state = _state(history=[{"experiment_id": "exp-000", "config_key": "x"}])
    out = ex.validate_proposal(_proposal(), state)
    assert out["experiment"]["feature_protocol"] == "metadata_fuel"
    assert out["experiment"]["weather_days"] == 5
    assert out["previous_decision"]["decision"] == "REJECT"


def test_weather_days_canonicalized_for_non_weather_protocol():
    a = ex.canonical_experiment({"model": "xgboost", "feature_protocol": "metadata", "weather_days": 2, "hyperparameters": {}})
    b = ex.canonical_experiment({"model": "xgboost", "feature_protocol": "metadata", "weather_days": 5, "hyperparameters": {}})
    assert a == b
    assert ex.config_key(a, 1) == ex.config_key(b, 1)
    c = ex.canonical_experiment({"model": "xgboost", "feature_protocol": "weather", "weather_days": 2, "hyperparameters": {}})
    assert c["weather_days"] == 2


def test_defaults_match_official_configs():
    lr = ex.canonical_experiment({"model": "logistic_regression", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {}})
    assert lr["hyperparameters"] == {"C": 1.0, "class_weight": "balanced"}
    xgb = ex.canonical_experiment({"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {}})
    hp = xgb["hyperparameters"]
    assert (hp["n_estimators"], hp["learning_rate"], hp["max_depth"], hp["subsample"], hp["colsample_bytree"], hp["scale_pos_weight"]) == (1000, 0.03, 4, 0.8, 0.8, "auto")


@pytest.mark.parametrize(
    "mutation",
    [
        {"model": "random_forest"},
        {"model": "xgboost; rm -rf /"},
        {"feature_protocol": "../../etc/passwd"},
        {"feature_protocol": "metadata_fuel_weather"},
        {"weather_days": True},
        {"weather_days": 6},
        {"weather_days": "5"},
        {"hyperparameters": {"C": float("nan")}},
        {"hyperparameters": {"C": float("inf")}},
        {"hyperparameters": {"C": 1000}},
        {"hyperparameters": {"C": "1.0"}},
        {"hyperparameters": {"class_weight": "heavy"}},
        {"hyperparameters": {"n_estimators": 100}},  # not an LR hyperparameter
        {"hyperparameters": {"shell": "echo"}},
        {"hyperparameters": "C=1"},
        {"command": "python train.py"},
    ],
)
def test_untrusted_experiment_rejected(mutation):
    exp = {"model": "logistic_regression", "feature_protocol": "metadata", "weather_days": 5, "hyperparameters": {}}
    exp.update(mutation)
    with pytest.raises(ex.ProposalError):
        ex.canonical_experiment(exp)


def test_xgboost_bounds_and_bool_rejection():
    base = {"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {}}
    for bad in [{"max_depth": 1}, {"max_depth": 11}, {"max_depth": 4.0}, {"max_depth": True}, {"learning_rate": 0}, {"scale_pos_weight": "balanced"}, {"scale_pos_weight": 100}]:
        e = copy.deepcopy(base)
        e["hyperparameters"] = bad
        with pytest.raises(ex.ProposalError):
            ex.canonical_experiment(e)
    ok = copy.deepcopy(base)
    ok["hyperparameters"] = {"scale_pos_weight": 5}
    assert ex.canonical_experiment(ok)["hyperparameters"]["scale_pos_weight"] == 5.0


def test_stale_revision_and_wrong_session_rejected():
    state = _state(history=[{"experiment_id": "exp-000", "config_key": "x"}])
    with pytest.raises(ex.ProposalError) as err:
        ex.validate_proposal(_proposal(state_revision=2), state)
    assert err.value.code == "stale_revision"
    with pytest.raises(ex.ProposalError) as err:
        ex.validate_proposal(_proposal(session_id="other"), state)
    assert err.value.code == "wrong_session"


def test_duplicate_configuration_rejected():
    exp = ex.canonical_experiment({"model": "logistic_regression", "feature_protocol": "metadata_fuel", "weather_days": 5, "hyperparameters": {"C": 1.0, "class_weight": "balanced"}})
    key = ex.config_key(exp, protocol.RESEARCH_SEED)
    state = _state(history=[{"experiment_id": "exp-000", "config_key": key}])
    with pytest.raises(ex.ProposalError) as err:
        ex.validate_proposal(_proposal(), state)
    assert err.value.code == "duplicate_experiment"


def test_duplicate_proposal_id_rejected():
    state = _state(history=[{"experiment_id": "exp-000", "config_key": "x"}])
    state["seen_proposal_ids"] = ["p-1"]
    with pytest.raises(ex.ProposalError) as err:
        ex.validate_proposal(_proposal(), state)
    assert err.value.code == "duplicate_proposal_id"


def test_decision_must_target_last_experiment():
    state = _state(history=[{"experiment_id": "exp-000", "config_key": "x"}, {"experiment_id": "exp-001", "config_key": "y"}])
    with pytest.raises(ex.ProposalError) as err:
        ex.validate_proposal(_proposal(), state)
    assert err.value.code == "wrong_decision_target"


def test_unknown_top_level_fields_and_missing_text_rejected():
    state = _state(history=[{"experiment_id": "exp-000", "config_key": "x"}])
    with pytest.raises(ex.ProposalError):
        ex.validate_proposal(_proposal(shell="echo hi"), state)
    with pytest.raises(ex.ProposalError):
        ex.validate_proposal(_proposal(hypothesis="   "), state)


def test_budget_exhausted_rejects_new_proposal():
    state = _state(history=[{"experiment_id": "exp-000", "config_key": "x"}], budget=0)
    with pytest.raises(ex.ProposalError) as err:
        ex.validate_proposal(_proposal(), state)
    assert err.value.code == "budget_exhausted"


def test_final_decision_validation():
    state = _state(history=[{"experiment_id": "exp-000", "config_key": "x"}, {"experiment_id": "exp-001", "config_key": "y"}])
    good = {"schema_version": 1, "session_id": "wf-test", "state_revision": 3, "experiment_id": "exp-001", "decision": "KEEP", "reason": "r", "learning": "l", "next_question": "q", "recommended_final_experiment_id": "exp-001"}
    out = ex.validate_final_decision(good, state)
    assert out["recommended_final_experiment_id"] == "exp-001"
    bad = dict(good, recommended_final_experiment_id="exp-999")
    with pytest.raises(ex.ProposalError):
        ex.validate_final_decision(bad, state)


def test_describe_change():
    a = ex.canonical_experiment({"model": "logistic_regression", "feature_protocol": "metadata", "weather_days": 5, "hyperparameters": {}})
    b = ex.canonical_experiment({"model": "xgboost", "feature_protocol": "metadata", "weather_days": 5, "hyperparameters": {}})
    assert ex.describe_change(a, b) == ["model logistic_regression -> xgboost"]
    assert ex.describe_change(None, a) == ["baseline"]


def test_manifest_lists_official_protocols():
    manifest = ex.capability_manifest()
    assert set(manifest["feature_protocols"]) == set(protocol.FEATURE_PROTOCOLS)
    assert "all" in manifest["feature_protocols"] and len(manifest["feature_protocols"]) == 21
    assert not math.isnan(manifest["models"]["xgboost"]["hyperparameters"]["learning_rate"]["default"])
