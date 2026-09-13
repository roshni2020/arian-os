"""Offline loop test: real lightweight training, SQLite persistence, restart recovery, budget and
final decision handling, using the explicitly labelled fallback stub (NOT ARIA) and no W&B."""
from __future__ import annotations

import json

import pytest

from wildfire_researcher import config, protocol
from wildfire_researcher.fallback import FallbackARIA
from wildfire_researcher.loop import ResearchLoop, replay_record
from wildfire_researcher.state import Store, numeric_best, research_state

needs_data = pytest.mark.skipif(not protocol.canonical_ready(), reason="canonical WildfireIA tables not downloaded")


def _session(store, budget=2, limit=1500):
    return store.create_session(session_id=None, budget=budget, aria_mode="fallback", research_seed=1, fast_mode=True, limit_train_samples=limit, entity="test-entity", project="test-project")


@needs_data
def test_full_loop_with_fallback_stub_persists_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACTS_DIR", tmp_path / "artifacts")
    store = Store(tmp_path / "db.sqlite")
    session = _session(store, budget=2)
    aria = FallbackARIA(session["id"], tmp_path / "aria")
    loop = ResearchLoop(store, session["id"], aria, tracking_enabled=False, wait_seconds=1, poll_seconds=1, log=lambda m: None)
    final = loop.run()
    assert final["status"] == "complete"
    exps = store.experiments(session["id"])
    assert [e["id"] for e in exps] == ["exp-000", "exp-001", "exp-002"]
    assert exps[0]["controller"] == "baseline_setup" and exps[1]["controller"] == "ARIA"
    assert all(e["status"] == "complete" and e["result"]["score_kind"] == "DEV_SCORE" for e in exps)
    # decisions recorded for every experiment (two from proposals, one final)
    assert [e["decision"] for e in exps] and all(e["decision"] in ("KEEP", "REJECT") for e in exps)
    assert final["final_decision"]["recommended_final_experiment_id"] in {e["id"] for e in exps}
    state = research_state(store, session["id"])
    assert state["remaining_budget"] == 0 and state["aria_mode"] == "fallback"
    assert state["state_revision"] >= 4
    # numeric best is independent of decisions
    best_id, best = numeric_best(exps)
    assert best == max(e["score"] for e in exps)
    # persisted state file exists and never mentions test-split metrics
    text = (tmp_path / "artifacts" / session["id"] / "state.json").read_text()
    assert '"test_auprc":' not in text and "predictions_test" not in text and "per_seed" not in text
    msgs = store.aria_messages(session["id"])
    assert sum(1 for m in msgs if m["direction"] == "inbound" and m["accepted"]) == 3
    # replay export reads stored records only
    record = replay_record(store, session["id"])
    assert len(record["experiments"]) == 3 and record["state"]["history"][-1]["score"] == exps[-1]["score"]
    json.dumps(record, default=str)


@needs_data
def test_restart_recovers_claimed_experiment_without_duplicating(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACTS_DIR", tmp_path / "artifacts")
    store = Store(tmp_path / "db.sqlite")
    session = _session(store, budget=1)
    aria = FallbackARIA(session["id"], tmp_path / "aria")
    loop = ResearchLoop(store, session["id"], aria, tracking_enabled=False, wait_seconds=1, poll_seconds=1, log=lambda m: None)
    loop.run_baseline()
    # Simulate a crash after ARIA's proposal was claimed but before training finished.
    validated, raw, meta = loop.await_proposal()
    claimed = store.claim_experiment(session["id"], experiment=validated["experiment"], config_key=validated["config_key"], controller="ARIA", proposal={"hypothesis": validated["hypothesis"]}, proposal_source=meta["artifact_ref"], parent_experiment_id="exp-000", change_summary="x")
    assert store.unfinished_experiment(session["id"])["id"] == claimed["id"]
    # A second worker process resumes: it must re-run exp-001, not create exp-002 for the same config.
    loop2 = ResearchLoop(store, session["id"], aria, tracking_enabled=False, wait_seconds=1, poll_seconds=1, log=lambda m: None)
    final = loop2.run()
    exps = store.experiments(session["id"])
    assert [e["id"] for e in exps] == ["exp-000", "exp-001"]
    assert exps[1]["status"] == "complete"
    assert final["status"] == "complete"


@needs_data
def test_cancel_stops_at_safe_point(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACTS_DIR", tmp_path / "artifacts")
    store = Store(tmp_path / "db.sqlite")
    session = _session(store, budget=3)
    aria = FallbackARIA(session["id"], tmp_path / "aria")
    loop = ResearchLoop(store, session["id"], aria, tracking_enabled=False, wait_seconds=1, poll_seconds=1, log=lambda m: None)
    loop.run_baseline()
    store.update_session(session["id"], cancel_requested=True)
    final = loop.run()
    assert final["status"] == "cancelled"
    assert len(store.completed_experiments(session["id"])) == 1
    # resume after cancel continues the same session instead of treating it as finished
    store.update_session(session["id"], cancel_requested=False)
    resumed = ResearchLoop(store, session["id"], aria, tracking_enabled=False, wait_seconds=1, poll_seconds=1, log=lambda m: None).run()
    assert resumed["status"] == "complete", resumed.get("error")
    assert len(store.completed_experiments(session["id"])) == 4


def test_duplicate_claim_is_rejected_by_database(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    session = _session(store)
    exp = {"model": "logistic_regression", "feature_protocol": "metadata", "weather_days": 5, "hyperparameters": {"C": 1.0, "class_weight": "balanced"}}
    store.claim_experiment(session["id"], experiment=exp, config_key="k1", controller="ARIA", proposal=None, proposal_source=None, parent_experiment_id=None, change_summary="a")
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        store.claim_experiment(session["id"], experiment=exp, config_key="k1", controller="ARIA", proposal=None, proposal_source=None, parent_experiment_id=None, change_summary="a")


def test_research_state_has_no_secrets_and_budget_semantics(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    session = _session(store, budget=4)
    state = research_state(store, session["id"])
    assert state["remaining_budget"] == 4 and state["budget"]["baseline_counts_toward_budget"] is False
    dumped = json.dumps(state)
    assert "WANDB_API_KEY" not in dumped and "api_key" not in dumped.lower()
    assert state["objective"]["published_benchmark"]["comparable_to_validation_scores"] is False
