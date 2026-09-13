import sqlite3
import pytest

from wildfire_researcher.benchmarks.storage import BenchmarkStore


@pytest.fixture
def store(tmp_path):
    return BenchmarkStore(tmp_path / "benchmarks.sqlite")


def sample(identifier="one"):
    return {"id": identifier, "title": "Climate prediction", "domain": "Climate",
            "dataset_identifier": "Acme/Data", "sources": [{"provider": "huggingface", "external_id": "Acme/Data", "external_url": "https://huggingface.co/datasets/Acme/Data"}]}


def test_source_dedup_and_missing_fields(store):
    first = store.upsert(sample())
    second = store.upsert({**sample("alternate"), "description": "Updated"})
    assert first["id"] == second["id"]
    assert store.get("alternate")["id"] == "one"
    assert store.list()["total"] == 1
    assert second["metric_name"] is None
    assert second["provenance"]["metric_name"]["status"] == "missing"
    assert len(second["sources"]) == 1


def test_project_snapshot_and_edits_survive_refresh(store):
    b = store.upsert(sample())
    p = store.create_project(b, "Review", 2, {"metric_name": "accuracy"})
    store.upsert({**sample(), "title": "Refreshed", "metric_name": "f1"})
    frozen = store.get_project(p["id"])["snapshot"]
    assert frozen["title"] == "Climate prediction"
    assert frozen["metric_name"] == "accuracy"
    assert frozen["provenance"]["metric_name"]["status"] == "user_edited"
    with pytest.raises(ValueError):
        store.create_project(b, "Bad", 1, {"compatibility": {"executable": True}})


def test_user_provenance_survives_upsert(store):
    store.upsert({**sample(), "metric_name": "f1", "provenance": {"metric_name": {"value": "f1", "status": "user_edited"}}})
    updated = store.upsert({**sample(), "metric_name": "accuracy"})
    assert updated["metric_name"] == "f1"
    assert updated["provenance"]["metric_name"]["status"] == "user_edited"


def test_result_selection_and_idempotency(store):
    b = store.upsert({**sample(), "results": [{"id": "a", "score": .4}, {"id": "b", "score": .6}]})
    with pytest.raises(ValueError, match="explicit"):
        store.create_project(b, "Review", 1)
    p = store.create_project(b, "Review", 1, selected_result_id="b", idempotency_key="request")
    assert p["snapshot"]["published_score"] == .6
    assert store.create_project(b, "Review", 1, selected_result_id="b", idempotency_key="request")["id"] == p["id"]
    with pytest.raises(ValueError, match="Idempotency"):
        store.create_project(b, "Changed", 1, selected_result_id="b", idempotency_key="request")
    assert store.link_session(p["id"], "session")["session_id"] == "session"
    assert store.link_session(p["id"], "session")["session_id"] == "session"
    with pytest.raises(ValueError):
        store.link_session(p["id"], "different")


def test_import_progress_and_filter(store):
    store.save_import({"id": "import", "status": "fetching", "benchmark": None})
    assert store.get_import("import")["status"] == "fetching"
    store.save_import({"id": "import", "status": "partial", "warnings": ["Interrupted"]})
    assert store.get_import("import")["status"] == "partial"
    store.upsert(sample())
    assert store.list(q="ACME", source="huggingface", domain="climate")["total"] == 1
    assert store.list(metric="f1")["total"] == 0


def test_abandoned_import_has_durable_retry_status(store):
    store.upsert(sample())
    store.save_import({"id": "abandoned", "status": "fetching", "created_at": "2000-01-01T00:00:00+00:00", "benchmark": None})
    result = store.get_import("abandoned")
    assert result["status"] == "failed" and "Retry" in result["warnings"][0]
    assert store.get_import("abandoned") == result
    late = dict(result, status="complete", warnings=[])
    assert store.finish_import(late)["status"] == "failed"
    assert store.get("one")["title"] == "Climate prediction"


def test_additive_migration_preserves_existing_and_source_history(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sessions (id TEXT)")
        db.execute("INSERT INTO sessions VALUES ('historic')")
    store = BenchmarkStore(path)
    store.upsert(sample())
    store.upsert({**sample(), "title": "New title"})
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT id FROM sessions").fetchone()[0] == "historic"
        assert db.execute("SELECT count(*) FROM benchmark_source_snapshots").fetchone()[0] == 2


def test_canonical_pins_not_replaced_by_shared_source(store):
    canonical = store.upsert({**sample("wildfireia"), "dataset_revision": "pinned"})
    updated = store.upsert({**sample("external"), "dataset_revision": "main"})
    assert updated["id"] == canonical["id"]
    assert updated["dataset_revision"] == "pinned"


def test_real_canonical_roundtrip_remains_executable(store):
    from wildfire_researcher.benchmarks.compatibility import wildfire_benchmark
    b = store.upsert(wildfire_benchmark())
    assert b["compatibility"]["executable"], b["compatibility"]["reasons"]
    p = store.create_project(b, "Wildfire", 1, selected_result_id=b["results"][0]["id"])
    assert p["compatibility"]["executable"], p["compatibility"]["reasons"]
    assert store.get_project(p["id"])["compatibility"]["executable"]
