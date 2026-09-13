"""Additive SQLite persistence for imported benchmark metadata and project snapshots."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid


FIELDS = tuple("slug title description domain task_type publication_date paper_url repository_url repository_public dataset_url dataset_public dataset_provider dataset_identifier dataset_revision metric_name metric_direction published_score published_model sample_count license train_split validation_split test_split evaluation_protocol leakage_notes source".split())
OVERRIDE_FIELDS = frozenset(FIELDS) - {"slug", "source", "dataset_public", "repository_public"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _source_key(source):
    provider = str(source.get("provider") or "").strip().lower()
    provider = {"hf": "huggingface", "hugging_face": "huggingface"}.get(provider, provider)
    external_id = str(source.get("external_id") or "").strip().rstrip("/")
    if provider in {"github", "huggingface", "doi"}:
        external_id = external_id.lower()
    if provider == "github" and external_id.endswith(".git"):
        external_id = external_id[:-4]
    if not provider or not external_id:
        raise ValueError("Source provider and external_id are required")
    return provider, external_id


def _decorate(value):
    from .compatibility import compatibility, readiness
    value = deepcopy(value)
    value["readiness"] = readiness(value)
    value["compatibility"] = compatibility(value)
    return value


class BenchmarkStore:
    """Each mutation commits atomically; existing scientific tables are untouched."""

    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._memory = sqlite3.connect(":memory:", check_same_thread=False) if self.path == ":memory:" else None
        with self._db(write=True) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS benchmark_records (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS benchmark_sources (
                    provider TEXT NOT NULL, external_id TEXT NOT NULL, benchmark_id TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(provider, external_id));
                CREATE TABLE IF NOT EXISTS benchmark_source_snapshots (
                    id INTEGER PRIMARY KEY, provider TEXT NOT NULL, external_id TEXT NOT NULL,
                    benchmark_id TEXT NOT NULL, captured_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS benchmark_field_provenance (
                    benchmark_id TEXT NOT NULL, field_name TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(benchmark_id, field_name));
                CREATE TABLE IF NOT EXISTS benchmark_results (
                    benchmark_id TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(benchmark_id, id));
                CREATE TABLE IF NOT EXISTS benchmark_imports (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS research_projects (
                    id TEXT PRIMARY KEY, benchmark_id TEXT NOT NULL, payload TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE, request_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS project_session_links (
                    project_id TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS benchmark_aliases (alias TEXT PRIMARY KEY, benchmark_id TEXT NOT NULL);
            """)

    @contextmanager
    def _db(self, write=False):
        db = self._memory or sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            if db is not self._memory:
                db.close()

    @staticmethod
    def _resolve(db, identifier):
        row = db.execute("SELECT benchmark_id FROM benchmark_aliases WHERE alias=?", (identifier,)).fetchone()
        return row[0] if row else identifier

    def upsert(self, benchmark):
        incoming = deepcopy(benchmark)
        requested_id = str(incoming.get("id") or uuid.uuid4())
        sources = incoming.get("sources") or []
        with self._db(write=True) as db:
            identifier = self._resolve(db, requested_id)
            matches = set()
            for source in sources:
                row = db.execute("SELECT benchmark_id FROM benchmark_sources WHERE provider=? AND external_id=?", _source_key(source)).fetchone()
                if row:
                    matches.add(row[0])
            if len(matches) > 1:
                raise ValueError("Sources belong to distinct benchmarks; explicit reconciliation required")
            if matches:
                identifier = matches.pop()
            row = db.execute("SELECT payload FROM benchmark_records WHERE id=?", (identifier,)).fetchone()
            old = json.loads(row[0]) if row else {}
            if identifier == "wildfireia" and requested_id != "wildfireia" and old:
                db.execute("INSERT OR REPLACE INTO benchmark_aliases VALUES (?,?)", (requested_id, identifier))
                return _decorate(old)
            value = {**old, **incoming, "id": identifier, "created_at": old.get("created_at") or _now(), "updated_at": _now()}
            for field in FIELDS:
                value.setdefault(field, None)
            value["slug"] = value.get("slug") or re.sub(r"[^a-z0-9]+", "-", (value.get("title") or identifier).lower()).strip("-")
            provenance = {**old.get("provenance", {}), **incoming.get("provenance", {})}
            for field in FIELDS:
                prior = old.get("provenance", {}).get(field, {})
                if prior.get("status") == "user_edited":
                    value[field] = old.get(field)
                    provenance[field] = prior
                elif field in incoming and field not in incoming.get("provenance", {}):
                    provenance[field] = {"value": value[field], "source_provider": None, "source_url": None,
                                         "status": "missing" if value[field] is None else "inferred", "confidence": None}
                provenance.setdefault(field, {"value": value[field], "source_provider": None, "source_url": None,
                                              "status": "missing" if value[field] is None else "inferred", "confidence": None})
                provenance[field]["value"] = value[field]
            value["provenance"] = provenance
            for source in sources:
                provider, external_id = _source_key(source)
                normalized = {**source, "provider": provider, "external_id": str(source["external_id"]).strip(), "last_synced_at": source.get("last_synced_at") or _now()}
                db.execute("INSERT OR REPLACE INTO benchmark_sources VALUES (?,?,?,?)", (provider, external_id, identifier, _dump(normalized)))
                db.execute("INSERT INTO benchmark_source_snapshots(provider,external_id,benchmark_id,captured_at,payload) VALUES (?,?,?,?,?)", (provider, external_id, identifier, _now(), _dump(incoming)))
            value["sources"] = [json.loads(r[0]) for r in db.execute("SELECT payload FROM benchmark_sources WHERE benchmark_id=? ORDER BY provider,external_id", (identifier,))]
            results = incoming.get("results", old.get("results", [])) or []
            normalized_results = []
            for result in results:
                item = {key: result.get(key) for key in "id model metric_name metric_direction metric_definition score dataset_identifier dataset_revision split source_url".split()}
                item["id"] = item.get("id") or hashlib.sha256(_dump(item).encode()).hexdigest()[:20]
                if not any(r["id"] == item["id"] for r in normalized_results):
                    normalized_results.append(item)
            value["results"] = normalized_results
            value = _decorate(value)
            db.execute("INSERT OR REPLACE INTO benchmark_records VALUES (?,?,?,?)", (identifier, _dump(value), value["created_at"], value["updated_at"]))
            if identifier != requested_id:
                db.execute("INSERT OR REPLACE INTO benchmark_aliases VALUES (?,?)", (requested_id, identifier))
            db.execute("DELETE FROM benchmark_field_provenance WHERE benchmark_id=?", (identifier,))
            db.executemany("INSERT INTO benchmark_field_provenance VALUES (?,?,?)", [(identifier, key, _dump(p)) for key, p in provenance.items()])
            db.execute("DELETE FROM benchmark_results WHERE benchmark_id=?", (identifier,))
            db.executemany("INSERT INTO benchmark_results VALUES (?,?,?)", [(identifier, r["id"], _dump(r)) for r in normalized_results])
            return value

    def get(self, identifier):
        with self._db() as db:
            row = db.execute("SELECT payload FROM benchmark_records WHERE id=?", (self._resolve(db, identifier),)).fetchone()
        if row is None:
            raise KeyError(identifier)
        return _decorate(json.loads(row[0]))

    def list(self, q="", source="", domain="", task_type="", metric="", sort="readiness", limit=50, offset=0):
        with self._db() as db:
            items = [_decorate(json.loads(row[0])) for row in db.execute("SELECT payload FROM benchmark_records")]
        q = q.strip().casefold()
        items = [b for b in items if (not q or q in " ".join(str(b.get(k) or "") for k in ("title", "description", "domain", "task_type", "dataset_identifier", "metric_name", "paper_url")).casefold())
                 and (not source or source.casefold() in {str(s.get("provider", "")).casefold() for s in b["sources"]} or source.casefold() == str(b.get("source") or "").casefold())
                 and (not domain or domain.casefold() == str(b.get("domain") or "").casefold())
                 and (not task_type or task_type.casefold() == str(b.get("task_type") or "").casefold())
                 and (not metric or metric.casefold() == str(b.get("metric_name") or "").casefold())]
        if sort == "smallest":
            items.sort(key=lambda b: (b.get("sample_count") is None, b.get("sample_count") or 0, b["id"]))
        elif sort == "newest":
            items.sort(key=lambda b: (b.get("publication_date") or "", b["id"]), reverse=True)
        elif sort == "popular":
            items.sort(key=lambda b: (b.get("popularity") or 0, b["id"]), reverse=True)
        else:
            items.sort(key=lambda b: (b["readiness"]["score"], b["id"]), reverse=True)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        def stale(b):
            try:
                return datetime.fromisoformat(b["updated_at"].replace("Z", "+00:00")) < cutoff
            except (ValueError, TypeError):
                return True
        return {"items": items[max(0, offset):max(0, offset) + max(0, min(limit, 200))], "total": len(items), "stale": any(stale(b) for b in items)}

    def save_import(self, record):
        value = deepcopy(record)
        value.setdefault("id", str(uuid.uuid4()))
        value.setdefault("created_at", _now())
        with self._db(write=True) as db:
            db.execute("INSERT OR REPLACE INTO benchmark_imports VALUES (?,?)", (value["id"], _dump(value)))
        return value

    def get_import(self, identifier):
        with self._db(write=True) as db:
            row = db.execute("SELECT payload FROM benchmark_imports WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError(identifier)
            record = json.loads(row[0])
            if record.get("status") == "fetching":
                try:
                    abandoned = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00")) < datetime.now(timezone.utc) - timedelta(minutes=10)
                except (KeyError, TypeError, ValueError):
                    abandoned = True
                if abandoned:
                    record.update(status="failed", warnings=["Import was interrupted or exceeded its processing window. Retry the source URL; saved benchmarks are preserved."])
                    db.execute("UPDATE benchmark_imports SET payload=? WHERE id=?", (_dump(record), identifier))
            return record

    def finish_import(self, record):
        """A late attempt cannot overwrite a terminal or recovered import record."""
        with self._db(write=True) as db:
            row = db.execute("SELECT payload FROM benchmark_imports WHERE id=?", (record["id"],)).fetchone()
            if row is None:
                raise KeyError(record["id"])
            current = json.loads(row[0])
            if current.get("status") != "fetching":
                return current
            db.execute("UPDATE benchmark_imports SET payload=? WHERE id=?", (_dump(record), record["id"]))
            return deepcopy(record)

    def create_project(self, benchmark, name, experiment_budget, overrides=None, selected_result_id=None, idempotency_key=None):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("Project name must contain 1 to 200 characters")
        if isinstance(experiment_budget, bool) or not isinstance(experiment_budget, int) or not 1 <= experiment_budget <= 50:
            raise ValueError("Experiment budget must be between 1 and 50")
        overrides = overrides or {}
        if set(overrides) - OVERRIDE_FIELDS:
            raise ValueError("Unsupported project override field")
        snapshot = self.get(benchmark) if isinstance(benchmark, str) else deepcopy(benchmark)
        request_hash = hashlib.sha256(_dump({"benchmark_id": snapshot["id"], "name": name, "experiment_budget": experiment_budget, "overrides": overrides, "selected_result_id": selected_result_id}).encode()).hexdigest()
        with self._db(write=True) as db:
            if idempotency_key:
                prior = db.execute("SELECT id,request_hash FROM research_projects WHERE idempotency_key=?", (idempotency_key,)).fetchone()
                if prior:
                    if prior["request_hash"] != request_hash:
                        raise ValueError("Idempotency key already used with different project input")
                    return self._project(db, prior["id"])
            results = snapshot.get("results") or []
            if len(results) > 1 and not selected_result_id:
                raise ValueError("Select an explicit published result")
            if selected_result_id:
                selected = next((r for r in results if r["id"] == selected_result_id), None)
                if selected is None:
                    raise ValueError("Selected result is not part of this benchmark")
                for field, key in {"published_score": "score", "published_model": "model", "metric_name": "metric_name", "metric_direction": "metric_direction"}.items():
                    if snapshot.get(field) == selected.get(key):
                        continue
                    snapshot[field] = selected.get(key)
                    snapshot.setdefault("provenance", {})[field] = {"value": selected.get(key), "source_provider": None, "source_url": selected.get("source_url"), "status": "inferred" if selected.get(key) is not None else "missing", "confidence": None}
            for field, value in overrides.items():
                snapshot[field] = deepcopy(value)
                snapshot.setdefault("provenance", {})[field] = {"value": deepcopy(value), "source_provider": None, "source_url": None, "status": "user_edited", "confidence": None}
            snapshot = _decorate(snapshot)
            project = {"id": str(uuid.uuid4()), "name": name.strip(), "benchmark_id": snapshot["id"], "snapshot": snapshot,
                       "experiment_budget": experiment_budget, "selected_result_id": selected_result_id, "session_id": None,
                       "created_at": _now(), "compatibility": snapshot["compatibility"]}
            db.execute("INSERT INTO research_projects VALUES (?,?,?,?,?)", (project["id"], snapshot["id"], _dump(project), idempotency_key or None, request_hash))
            return project

    @staticmethod
    def _project(db, identifier):
        row = db.execute("SELECT payload FROM research_projects WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        project = json.loads(row[0])
        link = db.execute("SELECT session_id FROM project_session_links WHERE project_id=?", (identifier,)).fetchone()
        project["session_id"] = link[0] if link else None
        project["compatibility"] = _decorate(project["snapshot"])["compatibility"]
        return project

    def projects(self):
        with self._db() as db:
            return [self._project(db, row[0]) for row in db.execute("SELECT id FROM research_projects ORDER BY rowid DESC").fetchall()]

    def get_project(self, identifier):
        with self._db() as db:
            return self._project(db, identifier)

    def link_session(self, project_id, session_id):
        with self._db(write=True) as db:
            project = self._project(db, project_id)
            if project["session_id"] and project["session_id"] != session_id:
                raise ValueError("Project already linked to another session")
            db.execute("INSERT OR IGNORE INTO project_session_links VALUES (?,?)", (project_id, session_id))
            linked = self._project(db, project_id)
            if linked["session_id"] != session_id:
                raise ValueError("Session already linked to another project")
            return linked
