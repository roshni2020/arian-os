from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from wildfire_researcher import api, config
from wildfire_researcher.execution_status import execution_status
from wildfire_researcher.state import Store

NOW = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "research.sqlite")
    result.create_session(session_id="wf-observation", budget=3, aria_mode="connected", research_seed=553371,
                          fast_mode=False, limit_train_samples=None, entity="test-entity", project="test-project")
    with result.connect() as db:
        db.execute("UPDATE sessions SET created_at=?,updated_at=?", (NOW.isoformat(), NOW.isoformat()))
        db.execute("UPDATE events SET ts=?", (NOW.isoformat(),))
    return result


def read(store, **kwargs):
    return execution_status(store, "wf-observation", now=NOW, **kwargs)


@pytest.mark.parametrize("status,stage", [("created", "idle"), ("awaiting_aria_proposal", "waiting_for_aria"),
    ("awaiting_final_decision", "waiting_for_aria"), ("training", "training"),
    ("validating_proposal", "validating"), ("evaluating", "evaluating"), ("final_evaluation", "finalizing")])
def test_stages_without_claiming_external_worker_dead(store, status, stage):
    store.update_session("wf-observation", status=status)
    result = read(store)
    assert result["transport"] == "local" and result["stage"] == stage
    assert result["local_worker"] == {"registered": False, "alive": None, "scope": "this_api_process"}
    assert not result["remote"]["verified"]
    assert result["remote"]["heartbeat_at"] is result["remote"]["queue_state"] is None
    assert not result["recovery"]["resume_available"]


def test_active_local_worker_is_scoped_observation(store):
    store.set_status("wf-observation", "training")
    result = read(store, local_worker=SimpleNamespace(is_alive=lambda: True))
    assert result["local_worker"]["alive"] is True
    assert result["recovery"]["cancel_available"]
    assert not result["recovery"]["resume_available"]
    assert result["started_at"]


def test_known_stopped_local_worker_can_resume_waiting_session(store):
    store.update_session("wf-observation", status="awaiting_aria_proposal")
    result = read(store, local_worker=SimpleNamespace(is_alive=lambda: False))
    assert result["recovery"]["resume_available"]
    assert "another process" in result["recovery"]["reason"]


@pytest.mark.parametrize("status,resume", [("complete", False), ("cancelled", True), ("error", True)])
def test_terminal_state_does_not_request_heartbeat(store, status, resume):
    store.update_session("wf-observation", status=status)
    result = read(store)
    assert result["terminal"] and result["activity"]["state"] == "terminal"
    assert result["recovery"]["resume_available"] is resume
    assert not result["recovery"]["cancel_available"]


def test_replay_never_offers_execution(store):
    store.update_session("wf-observation", aria_mode="replay", status="cancelled")
    assert not read(store)["recovery"]["resume_available"]


def test_terminal_local_thread_finishing_does_not_offer_conflicting_recovery(store):
    store.update_session("wf-observation", status="error")
    result = read(store, local_worker=SimpleNamespace(is_alive=lambda: True))
    assert not result["recovery"]["resume_available"]
    assert not result["recovery"]["cancel_available"]


def test_launch_refs_are_historical_and_never_imply_heartbeat(store, tmp_path):
    store.update_session("wf-observation", status="awaiting_aria_proposal", protocol_json=json.dumps({"execution_backend": "wandb-launch"}))
    folder = tmp_path / "operations" / "launch"
    folder.mkdir(parents=True)
    (folder / "setup.json").write_text(json.dumps({"session_id": "wf-observation", "queue": "q", "job": "e/p/job:v2", "agent_status": "running", "secret": "never-output"}))
    result = read(store, operations_dir=folder.parent)
    assert result["transport"] == "wandb-launch"
    assert result["launch_refs"]["queue"] == "q"
    assert result["remote"]["heartbeat_at"] is None
    assert not result["recovery"]["resume_available"]
    assert "local Resume is unsupported" in result["recovery"]["reason"]
    assert "never-output" not in json.dumps(result)
    (folder / "setup.json").write_text('{"session_id":"other", "queue":"wrong-session"}')
    assert read(store, operations_dir=folder.parent)["launch_refs"] is None


def test_stale_activity_not_replaced_by_poll_time(store):
    old = (NOW - timedelta(hours=1)).isoformat()
    with store.connect() as db:
        db.execute("UPDATE sessions SET status='training',updated_at=?", (old,))
        db.execute("UPDATE events SET ts=?", (old,))
    result = read(store)
    assert result["activity"]["state"] == "stale"
    assert result["activity"]["age_seconds"] == 3600
    assert result["last_event_at"] == result["last_activity_at"] == result["last_updated_at"] == old
    assert result["observed_at"] != old
    assert "not proof" in result["activity"]["detail"]


def test_missing_activity_and_start_remain_unknown(store):
    with store.connect() as db:
        db.execute("DELETE FROM events")
    result = read(store)
    assert result["activity"]["state"] == "no_heartbeat"
    assert result["last_event_at"] is result["last_activity_at"] is result["started_at"] is None


def test_session_row_update_does_not_hide_stale_activity(store):
    old = (NOW - timedelta(hours=1)).isoformat()
    with store.connect() as db:
        db.execute("UPDATE sessions SET status='training',updated_at=?", (NOW.isoformat(),))
        db.execute("UPDATE events SET ts=?", (old,))
    result = read(store)
    assert result["last_updated_at"] == NOW.isoformat()
    assert result["last_activity_at"] == old
    assert result["activity"]["age_seconds"] == 3600
    assert result["activity"]["state"] == "stale"


def test_newer_message_drives_exact_activity_timestamp_and_age(store):
    old = (NOW - timedelta(hours=1)).isoformat()
    recent = (NOW - timedelta(minutes=3)).isoformat()
    store.record_aria_message("wf-observation", direction="inbound", kind="proposal", artifact_ref=None,
                              artifact_digest=None, state_revision=None, accepted=None, feedback={"extra": "not-projected"}, payload={})
    with store.connect() as db:
        db.execute("UPDATE events SET ts=?", (old,))
        db.execute("UPDATE aria_messages SET ts=?", (recent,))
    result = read(store)
    assert result["last_event_at"] == old
    assert result["last_activity_at"] == recent
    assert result["activity"]["age_seconds"] == 180
    assert result["proposal_feedback"][0]["accepted"] is None
    assert result["proposal_feedback"][0]["state_revision"] is None
    assert result["proposal_feedback"][0]["feedback"] == {"code": None, "message": None}


def test_latest_bounded_events_feedback_and_budget_are_read_only(store):
    for number in range(32):
        store.log_event("wf-observation", "aria_nudge", str(number), {"secret": "not-returned"})
    store.log_event("wf-observation", "waiting", "repetitive wait")
    store.log_event("wf-observation", "traceback", "private trace")
    store.record_aria_message("wf-observation", direction="inbound", kind="proposal", artifact_ref="e/p/proposal:v3",
                              artifact_digest="digest", state_revision=3, accepted=False,
                              feedback={"code": "bad_model", "message": "Choose supported model", "raw": "not-returned"}, payload={"secret": "not-returned"})
    with store.connect() as db:
        for i in range(3):
            db.execute("INSERT INTO experiments (id,session_id,iteration,config_key,status,controller,experiment_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (f"exp-{i}", "wf-observation", i, str(i), "complete", "baseline" if i == 0 else "ARIA", "{}", NOW.isoformat(), NOW.isoformat()))
        before = list(db.iterdump())
    result = read(store)
    assert len(result["events"]) == 20 and result["events"][0]["message"] == "31"
    assert result["budget"] == {"max": 3, "used": 2, "remaining": 1, "baseline_excluded": True}
    assert result["proposal_feedback"][0]["feedback"] == {"code": "bad_model", "message": "Choose supported model"}
    assert "not-returned" not in json.dumps(result) and "private trace" not in json.dumps(result)
    with store.connect() as db:
        assert list(db.iterdump()) == before


def test_unknown_session_404_and_endpoint_does_not_control_workers(store, monkeypatch, tmp_path):
    monkeypatch.setattr(api, "_store", store)
    monkeypatch.setattr(api, "_workers", {})
    monkeypatch.setattr(config, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(api, "_start_worker", lambda *args: pytest.fail("Read must not start a worker"))
    with TestClient(api.app) as client:
        assert client.get("/api/sessions/missing/execution-status").status_code == 404
        result = client.get("/api/sessions/wf-observation/execution-status")
        assert result.status_code == 200
        assert result.json()["local_worker"]["alive"] is None
