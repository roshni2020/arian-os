"""If ARIA does not answer, the worker re-publishes the state (new revision) instead of choosing
an experiment itself, and gives up after the configured number of nudges."""
from __future__ import annotations

import pytest

from wildfire_researcher import config
from wildfire_researcher.aria_client import ARIATimeout
from wildfire_researcher.loop import ResearchLoop
from wildfire_researcher.state import Store


class SilentThenAnswering:
    """Stub: ignores the first revision it is asked about, answers at the next one."""

    def __init__(self):
        self.state = None
        self.asked = []

    def publish_state_local(self, state):
        self.state = state

    def wait_for(self, kind, revision, **_):
        self.asked.append(revision)
        if len(self.asked) < 2:
            raise ARIATimeout("silent")
        payload = {"schema_version": 1, "session_id": self.state["session_id"], "state_revision": revision, "experiment_id": "exp-000", "decision": "KEEP", "reason": "r", "learning": "l", "next_question": "q", "recommended_final_experiment_id": "exp-000"}
        return payload, {"artifact_ref": "local://stub", "artifact_digest": None}


def _session_with_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(config, "ARIA_NUDGE_SECONDS", 1)
    store = Store(tmp_path / "db.sqlite")
    session = store.create_session(session_id="wf-nudge", budget=0, aria_mode="fallback", research_seed=1, fast_mode=True, limit_train_samples=800, entity="e", project="p")
    # a completed baseline row without training
    store.claim_experiment(session["id"], experiment={"model": "logistic_regression", "feature_protocol": "metadata", "weather_days": 5, "hyperparameters": {"C": 1.0, "class_weight": "balanced"}}, config_key="k", controller="baseline_setup", proposal=None, proposal_source=None, parent_experiment_id=None, change_summary="baseline")
    store.update_experiment(session["id"], "exp-000", status="complete", result={"validation_auprc": 0.2, "score_kind": "DEV_SCORE", "validation_metrics": {}, "false_negative_count": 0, "false_positive_count": 0}, score=0.2, runtime_seconds=1.0)
    return store, session


def test_nudge_republishes_state_then_accepts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARIA_MAX_NUDGES", 2)
    store, session = _session_with_baseline(tmp_path, monkeypatch)
    aria = SilentThenAnswering()
    loop = ResearchLoop(store, session["id"], aria, tracking_enabled=False, wait_seconds=30, poll_seconds=1, log=lambda m: None)
    loop.publish_research_state(None, "test")  # r1
    final = loop.await_final_decision()
    assert final["decision"] == "KEEP"
    assert aria.asked == [1, 2], "worker must re-publish a new revision after silence, then accept the answer"
    kinds = [e["kind"] for e in store.events(session["id"])]
    assert "aria_nudge" in kinds
    assert store.get_session(session["id"])["state_revision"] == 2


def test_gives_up_after_max_nudges(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARIA_MAX_NUDGES", 1)
    store, session = _session_with_baseline(tmp_path, monkeypatch)

    class Silent(SilentThenAnswering):
        def wait_for(self, kind, revision, **_):
            self.asked.append(revision)
            raise ARIATimeout("silent")

    aria = Silent()
    loop = ResearchLoop(store, session["id"], aria, tracking_enabled=False, wait_seconds=5, poll_seconds=1, log=lambda m: None)
    loop.publish_research_state(None, "test")
    with pytest.raises(ARIATimeout):
        loop.await_final_decision()
    assert aria.asked == [1, 2]
    assert len(store.completed_experiments(session["id"])) == 1, "no experiment may be invented by the worker"
