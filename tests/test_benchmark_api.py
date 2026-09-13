"""Integration of catalog snapshots with the existing session boundary, without training."""
import pytest
from fastapi.testclient import TestClient
from wildfire_researcher import api, config, protocol
from wildfire_researcher.state import Store
from wildfire_researcher.benchmarks import routes


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_store", Store(tmp_path / "research.sqlite"))
    monkeypatch.setattr(api, "_workers", {})
    routes._catalogs.clear()
    return TestClient(api.app)


def test_vertical_slice(client, monkeypatch):
    catalog = client.get("/api/benchmarks?q=wildfire").json()
    assert catalog["total"] == 1
    b = client.get("/api/benchmarks/wildfireia").json()
    assert b["compatibility"]["executable"], b["compatibility"]
    req = {"benchmark_id": "wildfireia", "name": "Wildfire review", "experiment_budget": 1, "idempotency_key": "demo"}
    r = client.post("/api/projects", json=req)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["compatibility"]["executable"]
    assert client.post("/api/projects", json=req).json()["id"] == p["id"]
    assert api.store().list_sessions() == []
    calls = []
    monkeypatch.setattr(api, "_start_worker", lambda sid, wait: calls.append(sid))
    monkeypatch.setattr(config, "load_wandb_credential", lambda: None)
    monkeypatch.setattr(protocol, "canonical_ready", lambda: True)
    monkeypatch.setattr(protocol, "repo_commit", lambda: protocol.PINNED_COMMIT)
    r = client.post(f"/api/projects/{p['id']}/start", json={"wait_seconds": 10})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    assert calls == [sid]
    assert api.store().get_session(sid)["aria_mode"] == "connected"
    api.store().set_status(sid, "complete")
    again = client.post(f"/api/projects/{p['id']}/start", json={})
    assert again.json()["session_id"] == sid and calls == [sid]
    assert client.get(f"/api/sessions/{sid}/replay").status_code == 200


def test_altered_target_cannot_start(client):
    p = client.post("/api/projects", json={"benchmark_id": "wildfireia", "name": "edited", "overrides": {"published_score": 0.9}}).json()
    assert p["snapshot"]["provenance"]["published_score"]["status"] == "user_edited"
    assert client.post(f"/api/projects/{p['id']}/start", json={}).status_code == 409
    assert api.store().list_sessions() == []


def test_import_bad_urls_and_unknowns(client):
    for url in ["http://127.0.0.1/a", "https://github.com@127.0.0.1/a", "https://example.com/paper", "https://github.com/a/b?token=secret"]:
        assert client.post("/api/benchmarks/import", json={"url": url}).status_code == 400
    assert client.get("/api/benchmarks/nope").status_code == 404
    assert client.get("/api/projects/nope").status_code == 404


def test_sync_outage_retains_catalog(client, monkeypatch):
    from wildfire_researcher.benchmarks.providers import HuggingFaceProvider, ProviderError
    def fail(*args, **kwargs):
        raise ProviderError("Provider unavailable")
    monkeypatch.setattr(HuggingFaceProvider, "search", fail)
    r = client.post("/api/benchmarks/sync", json={"provider": "huggingface", "query": "wildfire"})
    assert r.status_code == 200 and r.json()["warnings"]
    assert client.get("/api/benchmarks/wildfireia").status_code == 200


def test_sync_returns_candidates_without_saving(client, monkeypatch):
    from wildfire_researcher.benchmarks.providers import HuggingFaceProvider
    candidate = {"id": "hf-candidate", "title": "Trending dataset", "dataset_identifier": "someone/trending",
                 "dataset_url": "https://huggingface.co/datasets/someone/trending",
                 "sources": [{"provider": "huggingface", "external_id": "someone/trending"}]}
    monkeypatch.setattr(HuggingFaceProvider, "search", lambda self, query="", limit=10: [dict(candidate)])
    before = client.get("/api/benchmarks").json()["total"]
    r = client.post("/api/benchmarks/sync", json={"provider": "huggingface", "query": "trending"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["saved"] is False and "readiness" in items[0]
    assert client.get("/api/benchmarks").json()["total"] == before
    assert client.get("/api/benchmarks/hf-candidate").status_code == 404


def test_sync_requires_a_query(client):
    assert client.post("/api/benchmarks/sync", json={"provider": "huggingface", "query": ""}).status_code == 422
    assert client.post("/api/benchmarks/sync", json={"provider": "huggingface"}).status_code == 422
