"""Deterministic scorers for the ARIA agent evaluation (no network)."""
from __future__ import annotations

from wildfire_researcher import agent_evals as ae
from wildfire_researcher import experiments as ex
from wildfire_researcher.state import Store

BASE = ex.canonical_experiment({"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {}})
DEPTH3 = ex.canonical_experiment({"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {"max_depth": 3}})


def _state():
    return {
        "session_id": "wf-t", "state_revision": 3, "research_seed": 1, "remaining_budget": 5, "seen_proposal_ids": [],
        "numeric_best": {"experiment_id": "exp-002", "validation_auprc": 0.483},
        "history": [
            {"experiment_id": "exp-000", "config_key": "a", "experiment": ex.canonical_experiment(ex.BASELINE_EXPERIMENT), "score": 0.1842, "delta_vs_previous_best": None, "decision": "KEEP"},
            {"experiment_id": "exp-002", "config_key": ex.config_key(BASE, 1), "experiment": BASE, "score": 0.483, "delta_vs_previous_best": 0.0858, "decision": None},
        ],
        "extra": {"false_negative_count": 235, "val_positives": 428},
    }


def _proposal(**over):
    p = {
        "schema_version": 1, "session_id": "wf-t", "state_revision": 3, "proposal_id": "p3",
        "observation": "exp-002 reached 0.4830 AUPRC and missed 235 of 428 positives.",
        "hypothesis": "Reducing max_depth from 4 to 3 will raise validation AUPRC above 0.4830.",
        "expected_result": "AUPRC at least 0.485.", "reason": "overfitting gap",
        "experiment": {"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {"max_depth": 3}},
        "previous_decision": {"experiment_id": "exp-002", "decision": "KEEP", "reason": "r", "learning": "l", "next_question": "q"},
    }
    p.update(over)
    return p


def test_contract_and_one_change_and_novelty():
    s = _state()
    assert ae.score_contract("proposal", s, _proposal())["valid"] is True
    assert ae.score_contract("proposal", s, _proposal(state_revision=2))["code"] == "stale_revision"
    assert ae.score_one_change("proposal", s, _proposal()) == {"one_change": True, "changes": 1, "changed": ["max_depth 4 -> 3"]}
    two = _proposal(experiment={"model": "xgboost", "feature_protocol": "all_without_fire", "weather_days": 5, "hyperparameters": {"max_depth": 3}})
    assert ae.score_one_change("proposal", s, two)["changes"] == 2
    assert ae.score_novelty("proposal", s, _proposal())["novel"] is True
    dup = _proposal(experiment={"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {}})
    assert ae.score_novelty("proposal", s, dup)["novel"] is False


def test_grounding_uses_numbers_from_state():
    nums = ae.state_numbers(_state())
    assert 0.483 in nums and 235.0 in nums and 428.0 in nums
    g = ae.score_grounded(_proposal(), nums)
    assert g["grounded_fraction"] == 1.0 and g["cited"] >= 3
    bad = ae.score_grounded(_proposal(observation="exp-002 reached 0.4830 and missed 999 of 428 positives."), nums)
    assert bad["ungrounded"] == ["999"] and 0 < bad["grounded_fraction"] < 1
    # derived numbers (a gap or delta between two state numbers) count as grounded
    derived = ae.score_grounded(_proposal(observation="the gain over the 0.1842 baseline is 0.2988 and 193 positives remain."), nums)
    assert derived["ungrounded"] == [] and derived["derived"] >= 2
    # targets in the hypothesis are not grounding claims
    assert ae.score_grounded(_proposal(observation="", hypothesis="reach 0.999"), nums)["cited"] == 0


def test_decision_consistency_and_noise():
    decided = {"experiment_id": "exp-003", "score": 0.4867, "delta_vs_previous_best": 0.0037, "previous_best": 0.483}
    d = ae.score_decision("proposal", _proposal(previous_decision={"experiment_id": "exp-003", "decision": "KEEP", "reason": "r", "learning": "l"}), decided)
    assert d["consistent"] is True and d["within_noise"] is False
    noisy = dict(decided, delta_vs_previous_best=0.001)
    d = ae.score_decision("decision", {"decision": "REJECT"}, noisy)
    assert d["consistent"] is False and d["within_noise"] is True
    assert ae.score_decision("decision", {"decision": "KEEP"}, {"experiment_id": "exp-000", "score": 0.18, "delta_vs_previous_best": None, "previous_best": None})["consistent"] is True


def test_prediction_direction_and_target():
    resulting = {"experiment_id": "exp-003", "score": 0.4867, "delta_vs_previous_best": 0.0037, "previous_best": 0.483}
    p = ae.score_prediction("proposal", _proposal(), resulting)
    assert p == {"direction_hit": True, "target": 0.485, "target_hit": True, "measured": 0.4867}
    miss = ae.score_prediction("proposal", _proposal(expected_result="AUPRC above 0.50"), resulting)
    assert miss["target_hit"] is False
    assert ae.score_prediction("decision", {}, None)["direction_hit"] is None


def test_build_rows_from_store(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    sid = store.create_session(session_id="wf-t", budget=3, aria_mode="connected", research_seed=1, fast_mode=False, limit_train_samples=None, entity="e", project="p")["id"]
    base = ex.canonical_experiment(ex.BASELINE_EXPERIMENT)
    store.claim_experiment(sid, experiment=base, config_key="a", controller="baseline_setup", proposal=None, proposal_source=None, parent_experiment_id=None, change_summary="baseline")
    store.update_experiment(sid, "exp-000", status="complete", score=0.1842, result={"validation_auprc": 0.1842})
    prop = _proposal(proposal_id="p1", state_revision=1, previous_decision={"experiment_id": "exp-000", "decision": "KEEP", "reason": "r", "learning": "l"}, experiment={"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {}})
    store.record_aria_message(sid, direction="inbound", kind="proposal", artifact_ref="ref1", artifact_digest="d", state_revision=1, accepted=True, feedback=None, payload=prop)
    store.claim_experiment(sid, experiment=BASE, config_key="b", controller="ARIA", proposal={"proposal_id": "p1", "hypothesis": "h"}, proposal_source="ref1", parent_experiment_id="exp-000", change_summary="x")
    store.update_experiment(sid, "exp-001", status="complete", score=0.483, previous_best=0.1842, delta=0.2988, result={"validation_auprc": 0.483})
    states = {1: {"session_id": sid, "state_revision": 1, "research_seed": 1, "remaining_budget": 3, "seen_proposal_ids": [], "numeric_best": {"experiment_id": "exp-000", "validation_auprc": 0.1842}, "history": [{"experiment_id": "exp-000", "iteration": 0, "config_key": "a", "experiment": base, "score": 0.1842, "delta_vs_previous_best": None, "decision": None}]}}
    rows = ae.build_rows(store, sid, lambda s, rev: states.get(rev))
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "proposal" and row["resulting"]["experiment_id"] == "exp-001" and row["decided"]["experiment_id"] == "exp-000"
    scored = ae.score_rows(rows)
    card = ae.scorecard(scored)
    assert card["contract_valid_rate"] == 1.0 and card["one_change_rate"] is not None and card["prediction_direction_hit_rate"] == 1.0
