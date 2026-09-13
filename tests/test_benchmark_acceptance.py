"""Independent acceptance checks; all databases are isolated, no training/network."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import sqlite3

import pytest

from wildfire_researcher.benchmarks.compatibility import wildfire_benchmark
from wildfire_researcher.benchmarks.storage import BenchmarkStore
from wildfire_researcher.state import Store


@pytest.fixture
def catalog(tmp_path):
    return BenchmarkStore(tmp_path / "acceptance.sqlite")


def test_migration_preserves_existing_records_and_schema(tmp_path):
    path = tmp_path / "history.sqlite"
    legacy = Store(path)
    legacy.create_session(session_id="historical", budget=1, aria_mode="connected",
                          research_seed=553371, fast_mode=False, limit_train_samples=None,
                          entity="test", project="test")
    legacy.update_session("historical", status="complete", final_evaluation={
        "benchmark_beaten": True, "mean_test_auprc": 0.54, "historical": True})
    with sqlite3.connect(path) as db:
        tables = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'").fetchall()
        before = {name: db.execute(f'SELECT * FROM "{name}"').fetchall() for name, _ in tables}
    for _ in range(2):
        BenchmarkStore(path).upsert(wildfire_benchmark())
    with sqlite3.connect(path) as db:
        for name, sql in tables:
            assert db.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0] == sql
            assert db.execute(f'SELECT * FROM "{name}"').fetchall() == before[name]


def test_saved_snapshot_survives_refresh_and_keeps_user_provenance(catalog):
    b = catalog.upsert(wildfire_benchmark())
    p = catalog.create_project(b, "Reviewed project", 2, overrides={"description": "My notes"})
    before = deepcopy(p["snapshot"])
    updated = wildfire_benchmark()
    updated["description"] = "Source changed after review"
    catalog.upsert(updated)
    after = catalog.get_project(p["id"])
    assert after["snapshot"] == before
    assert after["snapshot"]["provenance"]["description"]["status"] == "user_edited"
    assert catalog.get(b["id"])["description"] == updated["description"]
    assert after["session_id"] is None


def test_concurrent_idempotency_creates_one_project(catalog):
    b = catalog.upsert(wildfire_benchmark())
    def create(_):
        return catalog.create_project(b, "Identical request", 1, idempotency_key="one-request")["id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(create, range(8)))
    assert len(set(ids)) == 1
    assert len(catalog.projects()) == 1
    with pytest.raises(ValueError, match="[Ii]dempotency"):
        catalog.create_project(b, "Different request", 1, idempotency_key="one-request")
    assert len(catalog.projects()) == 1


def test_multiple_results_require_explicit_selection_and_retain_context(catalog):
    results = [{"id": "result-a", "model": "model-a", "metric_name": "AP",
                "metric_direction": "maximize", "metric_definition": "average_precision_score",
                "score": 0.4, "dataset_identifier": "example/data", "dataset_revision": "revision-a",
                "split": "validation", "source_url": "https://example.org/paper"},
               {"id": "result-b", "model": "model-b", "metric_name": "accuracy",
                "metric_direction": "maximize", "metric_definition": "fraction correct",
                "score": 0.8, "dataset_identifier": "example/data", "dataset_revision": "revision-b",
                "split": "test", "source_url": "https://example.org/paper"}]
    b = catalog.upsert({"id": "multiple", "title": "Multiple targets", "results": results})
    with pytest.raises(ValueError, match="explicit"):
        catalog.create_project(b, "Needs review", 1)
    with pytest.raises(ValueError, match="not part"):
        catalog.create_project(b, "Unknown result", 1, selected_result_id="missing")
    p = catalog.create_project(b, "Reviewed", 1, selected_result_id="result-b")
    assert p["snapshot"]["published_score"] == 0.8
    assert p["snapshot"]["published_model"] == "model-b"
    assert p["snapshot"]["results"] == results
    assert not p["compatibility"]["executable"]


def test_source_conflict_rolls_back_entire_mutation(catalog):
    a = catalog.upsert({"id": "a", "title": "First", "sources": [{"provider": "github", "external_id": "owner/a"}]})
    b = catalog.upsert({"id": "b", "title": "Second", "sources": [{"provider": "github", "external_id": "owner/b"}]})
    with pytest.raises(ValueError, match="distinct"):
        catalog.upsert({"id": "collision", "title": "Invalid merge", "sources": a["sources"] + b["sources"]})
    assert catalog.get("a")["title"] == "First"
    assert catalog.get("b")["title"] == "Second"
    assert catalog.list()["total"] == 2


def test_interrupted_invalid_import_does_not_leave_source_or_alias(catalog):
    with pytest.raises(ValueError):
        catalog.upsert({"id": "invalid", "published_score": float("nan"),
                        "sources": [{"provider": "github", "external_id": "owner/broken"}]})
    assert catalog.list()["total"] == 0
    with sqlite3.connect(catalog.path) as db:
        for table in ("benchmark_sources", "benchmark_source_snapshots", "benchmark_aliases"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_partial_metadata_keeps_missing_values_and_zero_score(catalog):
    b = catalog.upsert({"id": "partial", "title": "Partial dataset", "published_score": 0.0})
    assert b["published_score"] == 0.0
    assert b["dataset_revision"] is None and b["metric_name"] is None
    assert b["provenance"]["metric_name"]["status"] == "missing"
    assert b["readiness"]["status"] == "partial"
    assert "published_score" not in b["readiness"]["missing"]
    assert not b["compatibility"]["executable"]


def test_search_filters_and_paging_are_stable(catalog):
    for identity, size in (("one", 10), ("two", 20), ("three", None)):
        catalog.upsert({"id": identity, "title": "Medical classification " + identity,
                        "domain": "healthcare", "task_type": "classification", "metric_name": "AP",
                        "sample_count": size, "source": "openml"})
    result = catalog.list(q=" MEDICAL ", domain="HEALTHCARE", metric="ap", source="openml", sort="smallest", limit=1, offset=1)
    assert result["total"] == 3 and result["items"][0]["id"] == "two"
    assert catalog.list(q="not-present")["total"] == 0


def test_session_links_are_unique_and_recoverable(catalog):
    b = catalog.upsert(wildfire_benchmark())
    first = catalog.create_project(b, "One", 1)
    second = catalog.create_project(b, "Two", 1)
    catalog.link_session(first["id"], "existing-session")
    assert catalog.link_session(first["id"], "existing-session")["session_id"] == "existing-session"
    with pytest.raises(ValueError):
        catalog.link_session(first["id"], "other-session")
    with pytest.raises(ValueError):
        catalog.link_session(second["id"], "existing-session")
    assert catalog.get_project(second["id"])["session_id"] is None


def test_metadata_completeness_does_not_grant_an_executor(catalog):
    b = catalog.upsert({"id": "unsupported-complete", "title": "Unsupported complete metadata",
        "dataset_url": "https://example.org/data", "dataset_public": True, "metric_name": "AP", "published_score": 0.5,
        "train_split": "train", "validation_split": "validation", "test_split": "test",
        "repository_url": "https://github.com/example/benchmark", "repository_public": True,
        "evaluation_protocol": {"evaluation_script": "https://github.com/example/benchmark/blob/main/eval.py",
                                "data_splits_url": "https://example.org/splits"}})
    assert b["readiness"]["score"] == 6
    assert not b["compatibility"]["executable"]
    without_evidence = deepcopy(b)
    without_evidence["evaluation_protocol"] = {"metric_definition": "AP"}
    without_evidence["validation_split"] = None
    without_evidence["metric_direction"] = "maximize"
    less_ready = catalog.upsert(without_evidence)
    assert less_ready["readiness"]["status"] == "partial"
    assert less_ready["readiness"]["score"] < 6


def test_abandoned_import_recovers_without_changing_saved_metadata(catalog):
    b = catalog.upsert(wildfire_benchmark())
    before = catalog.get(b["id"])
    catalog.save_import({"id": "abandoned", "status": "fetching", "benchmark": None,
                         "warnings": [], "created_at": "2000-01-01T00:00:00+00:00"})
    recovered = catalog.get_import("abandoned")
    assert recovered["status"] == "failed" and recovered["warnings"]
    assert catalog.get_import("abandoned") == recovered
    assert catalog.finish_import({**recovered, "status": "complete", "warnings": []}) == recovered
    assert catalog.get_import("abandoned")["status"] == "failed"
    assert catalog.get(b["id"]) == before
    assert catalog.projects() == []


def test_queued_import_does_not_start_durable_expiry_window(catalog, monkeypatch):
    import threading
    from wildfire_researcher.benchmarks import service
    classified = threading.Event()
    original = service.classify_url
    def classify(value):
        result = original(value)
        classified.set()
        return result
    class Provider:
        def get_benchmark(self, identity):
            return {"id": "queued", "title": "Queued import", "dataset_identifier": identity}
    monkeypatch.setattr(service, "classify_url", classify)
    monkeypatch.setattr(service, "provider_for", lambda _: Provider())
    results = []
    with service._refresh_lock:
        worker = threading.Thread(target=lambda: results.append(service.import_url(catalog, "https://huggingface.co/datasets/example/queued")))
        worker.start()
        assert classified.wait(2)
        with sqlite3.connect(catalog.path) as db:
            assert db.execute("SELECT COUNT(*) FROM benchmark_imports").fetchone()[0] == 0
    worker.join(5)
    assert not worker.is_alive()
    assert len(results) == 1 and results[0]["status"] == "partial"
