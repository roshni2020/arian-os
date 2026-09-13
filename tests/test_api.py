"""API tests with the fallback stub (NOT ARIA) and no W&B: start/status/details/replay/persistence."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from wildfire_researcher import api, config, protocol
from wildfire_researcher.state import Store

needs_data = pytest.mark.skipif(not protocol.canonical_ready(), reason="canonical WildfireIA tables not downloaded")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(api, "_store", Store(tmp_path / "db.sqlite"))
    api._workers.clear()
    return TestClient(api.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_unknown_session_404(client):
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.get("/api/sessions/nope/experiments/exp-000").status_code == 404


def test_start_rejects_bad_mode(client):
    r = client.post("/api/sessions", json={"aria_mode": "magic"})
    assert r.status_code == 422


@needs_data
def test_start_fallback_session_runs_and_persists(client):
    r = client.post("/api/sessions", json={"budget": 1, "aria_mode": "fallback", "limit_train_samples": 1200, "wait_seconds": 10})
    assert r.status_code == 200, r.text
    sid = r.json()["session"]["id"]
    assert r.json()["mode_label"] == "DEVELOPMENT FALLBACK (NOT ARIA)"
    deadline = time.time() + 300
    status = None
    while time.time() < deadline:
        view = client.get(f"/api/sessions/{sid}").json()
        status = view["session"]["status"]
        if status in {"complete", "error", "cancelled"}:
            break
        time.sleep(1)
    assert status == "complete", view["session"].get("error")
    exps = view["experiments"]
    assert len(exps) == 2 and all(e["result"]["score_kind"] == "DEV_SCORE" for e in exps)
    assert view["benchmark"]["beaten"] is False
    assert view["benchmark"]["published_test_auprc"] == 0.533
    detail = client.get(f"/api/sessions/{sid}/experiments/exp-001").json()
    assert detail["controller"] == "ARIA" and detail["decision"] in ("KEEP", "REJECT")
    events = client.get(f"/api/sessions/{sid}/events").json()
    assert any(e["kind"] == "experiment_complete" for e in events)
    replay = client.get(f"/api/sessions/{sid}/replay").json()
    assert len(replay["experiments"]) == 2
    # "refresh": a fresh store on the same file sees the same history
    fresh = Store(api._store.path)
    assert [e["id"] for e in fresh.experiments(sid)] == ["exp-000", "exp-001"]
    assert client.post("/api/sessions/{}/resume".format(sid)).status_code == 400


def test_automation_prompt_under_limit(client, tmp_path):
    s = api.store().create_session(session_id="wf-prompt", budget=3, aria_mode="connected", research_seed=1, fast_mode=False, limit_train_samples=None, entity="e", project="p")
    r = client.get(f"/api/automation-prompt/{s['id']}").json()
    assert r["chars"] < 4000 and "<SESSION>-state:latest" in r["prompt"] and r["generic"] is True
    r = client.get(f"/api/automation-prompt/{s['id']}?generic=false").json()
    assert "wf-prompt-state:latest" in r["prompt"] and r["run_name_regex"].startswith("^wf-prompt-")
