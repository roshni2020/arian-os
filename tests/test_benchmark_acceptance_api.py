"""Independent HTTP contract checks; worker dispatch is intercepted, never trained."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from wildfire_researcher import api, config, protocol
from wildfire_researcher.state import Store
from wildfire_researcher.benchmarks import routes, service
from wildfire_researcher.benchmarks.compatibility import wildfire_benchmark
from wildfire_researcher.benchmarks.providers import ProviderError


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_store", Store(tmp_path / "api.sqlite"))
    monkeypatch.setattr(api, "_workers", {})
    monkeypatch.setattr(routes, "_catalogs", {})
    monkeypatch.setattr(config, "ARTIFACTS_DIR", tmp_path / "artifacts")
    def forbidden(*args, **kwargs):
        raise AssertionError("No implicit research execution or provider fetch")
    monkeypatch.setattr(api, "_start_worker", forbidden)
    monkeypatch.setattr(service, "provider_for", forbidden)
    return TestClient(api.app)


def test_catalog_and_project_creation_are_offline_and_do_not_start(client):
    result = client.get("/api/benchmarks?q=wildfire")
    assert result.status_code == 200
    b = result.json()["items"][0]
    assert b["compatibility"]["executable"], b["compatibility"]
    created = client.post("/api/projects", json={"benchmark_id": b["id"], "name": "Review", "experiment_budget": 1})
    assert created.status_code == 200, created.text
    assert created.json()["session_id"] is None
    assert api.store().list_sessions() == []
    assert client.get("/api/projects/" + created.json()["id"]).json() == created.json()


def test_explicit_official_result_selection_still_allows_pinned_executor(client):
    b = client.get("/api/benchmarks/wildfireia").json()
    p = client.post("/api/projects", json={"benchmark_id": b["id"], "name": "Selected official result",
        "experiment_budget": 1, "selected_result_id": b["results"][0]["id"]})
    assert p.status_code == 200, p.text
    assert p.json()["compatibility"]["executable"], p.json()["compatibility"]


@pytest.mark.parametrize("override", [
    {"dataset_revision": "main"}, {"metric_name": "AUROC"}, {"published_score": 0.9},
    {"train_split": "random"}, {"evaluation_protocol": {}}, {"repository_url": "https://github.com/example/repo"},
])
def test_altered_project_cannot_start(client, override):
    p = client.post("/api/projects", json={"benchmark_id": "wildfireia", "name": "Altered",
        "experiment_budget": 1, "overrides": override}).json()
    assert not p["compatibility"]["executable"]
    response = client.post(f'/api/projects/{p["id"]}/start', json={})
    assert response.status_code == 409, response.text
    assert api.store().list_sessions() == []


def test_valid_start_uses_existing_connected_session_and_is_idempotent(client, monkeypatch):
    monkeypatch.setattr(protocol, "canonical_ready", lambda: True)
    monkeypatch.setattr(protocol, "repo_commit", lambda: protocol.PINNED_COMMIT)
    monkeypatch.setattr(config, "load_wandb_credential", lambda: None)
    dispatched = []
    def dispatch(sid, wait):
        dispatched.append(sid)
        api.store().set_status(sid, "awaiting_aria_proposal")
    monkeypatch.setattr(api, "_start_worker", dispatch)
    p = client.post("/api/projects", json={"benchmark_id": "wildfireia", "name": "Start", "experiment_budget": 1}).json()
    first = client.post(f'/api/projects/{p["id"]}/start', json={"wait_seconds": 10})
    assert first.status_code == 200, first.text
    second = client.post(f'/api/projects/{p["id"]}/start', json={"wait_seconds": 10})
    assert second.status_code == 200, second.text
    assert second.json()["session_id"] == first.json()["session_id"]
    assert dispatched == [first.json()["session_id"]]
    session = api.store().get_session(dispatched[0])
    assert session["aria_mode"] == "connected" and session["limit_train_samples"] is None
    assert session["research_seed"] == protocol.RESEARCH_SEED
    assert session["final_evaluation"] is None


def test_provider_failure_preserves_catalog_and_sanitizes_error(client, monkeypatch):
    class FailingProvider:
        def search(self, *args, **kwargs):
            raise ProviderError("SECRET upstream diagnostic")
        def get_benchmark(self, *args, **kwargs):
            raise ProviderError("SECRET upstream diagnostic")
    monkeypatch.setattr(service, "provider_for", lambda _: FailingProvider())
    before = client.get("/api/benchmarks").json()
    refreshed = client.post("/api/benchmarks/sync", json={"provider": "huggingface", "query": "wildfire"})
    assert refreshed.status_code == 200 and refreshed.json()["warnings"]
    assert "SECRET" not in refreshed.text
    imported = client.post("/api/benchmarks/import", json={"url": "https://huggingface.co/datasets/example/missing"})
    assert imported.json()["status"] == "failed" and "SECRET" not in imported.text
    assert client.get("/api/benchmarks").json() == before
    assert client.get("/api/benchmarks/imports/" + imported.json()["id"]).json() == imported.json()


def test_partial_import_can_be_reviewed_without_becoming_runnable(client, monkeypatch):
    class PartialProvider:
        def get_benchmark(self, identity):
            return {"id": "partial", "title": "Metadata only", "dataset_identifier": identity,
                    "sources": [{"provider": "huggingface", "external_id": identity}]}
    monkeypatch.setattr(service, "provider_for", lambda _: PartialProvider())
    imported = client.post("/api/benchmarks/import", json={"url": "https://huggingface.co/datasets/example/partial"})
    assert imported.status_code == 200 and imported.json()["status"] == "partial"
    p = client.post("/api/projects", json={"benchmark_id": "partial", "name": "Review missing target", "experiment_budget": 1,
        "overrides": {"published_score": 0.5, "metric_name": "AUPRC"}}).json()
    assert p["snapshot"]["provenance"]["published_score"]["status"] == "user_edited"
    assert not p["compatibility"]["executable"]
    assert client.post(f'/api/projects/{p["id"]}/start', json={}).status_code == 409


def test_existing_custom_session_project_preserves_history_and_stays_nonrunnable(client):
    session = api.store().create_session(session_id="custom-existing", budget=1, aria_mode="fallback",
        research_seed=1, fast_mode=True, limit_train_samples=200, entity="test", project="test")
    before = api.store().get_session(session["id"])
    body = {"session_id": session["id"], "name": "Saved custom research"}
    first = client.post("/api/projects/from-session", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["session_id"] == session["id"]
    assert not first.json()["compatibility"]["executable"]
    assert api.store().get_session(session["id"]) == before
    second = client.post("/api/projects/from-session", json=body)
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"]
    assert client.post(f'/api/projects/{first.json()["id"]}/start', json={}).status_code == 409


def test_existing_connected_session_with_different_protocol_is_not_marked_runnable(client):
    session = api.store().create_session(session_id="custom-different", budget=1, aria_mode="connected",
        research_seed=123, fast_mode=False, limit_train_samples=None,
        entity=config.WANDB_ENTITY, project=config.WANDB_PROJECT)
    response = client.post("/api/projects/from-session", json={"session_id": session["id"], "name": "Different seed"})
    assert response.status_code == 200, response.text
    assert not response.json()["compatibility"]["executable"], "Saved custom identity must not claim the canonical execution configuration"


def test_unknown_custom_session_cannot_create_project(client):
    assert client.post("/api/projects/from-session", json={"session_id": "unknown", "name": "Unknown"}).status_code == 404
    assert client.get("/api/projects").json()["items"] == []

