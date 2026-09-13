"""Structured, metadata-only OpenML task/dataset imports.

API documentation: https://docs.openml.org/ecosystem/Rest/
Task schema: https://docs.openml.org/reference/tasks/task/
"""
from datetime import datetime, timezone
import math
import re
from urllib.parse import quote, urlencode, urlsplit

from .providers import FIELDS, ProviderError, credential, safe_json

API = "https://www.openml.org/api/v1/json/"


def _text(value):
    return value.strip()[:20000] if isinstance(value, str) and value.strip() else None


def _number(value):
    try:
        value = float(value)
        return int(value) if math.isfinite(value) and value >= 0 and value.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def _id(value):
    if not re.fullmatch(r"[1-9][0-9]{0,9}", str(value)):
        raise ProviderError("Invalid OpenML identifier")
    return str(value)


def _link(value):
    if not isinstance(value, str) or len(value) > 2000 or any(ord(c) < 33 for c in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        return value
    except ValueError:
        return None


def _list(value):
    return value if isinstance(value, list) else [value] if isinstance(value, dict) else []


def _inputs(task):
    values = {}
    for entry in _list(task.get("input")):
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ProviderError("Invalid OpenML task metadata")
        if entry["name"] in values:
            raise ProviderError("Invalid OpenML task metadata")
        values[entry["name"]] = entry
    return values


def normalize_openml(data: dict, task: dict | None = None, qualities: list | None = None) -> dict:
    if not isinstance(data, dict):
        raise ProviderError("Invalid OpenML dataset metadata")
    if task is not None and not isinstance(task, dict):
        raise ProviderError("Invalid OpenML task metadata")
    did = _id(data.get("id", data.get("did")))
    if data.get("visibility") not in (None, "public"):
        raise ProviderError("Only public OpenML datasets may be imported")
    tid = _id(task.get("task_id")) if task else None
    external_id = ("t/" + tid) if tid else ("d/" + did)
    dataset_url = "https://www.openml.org/d/" + did
    source_url = "https://www.openml.org/" + external_id
    now = datetime.now(timezone.utc).isoformat()
    b = dict.fromkeys(FIELDS)
    b.update(id="openml-" + external_id.replace("/", "-"), slug="openml-" + external_id.replace("/", "-"),
             title=_text(task.get("task_name")) if task else _text(data.get("name")),
             description=_text(data.get("description")), dataset_url=dataset_url,
             dataset_public=True if data.get("visibility") == "public" or data.get("status") == "active" else None,
             repository_public=None,
             dataset_provider="openml", dataset_identifier="d/" + did,
             dataset_revision=str(data["version"]) if isinstance(data.get("version"), (str, int)) else None,
             license=_text(data.get("licence")), paper_url=_link(data.get("paper_url")),
             source="openml", created_at=now, updated_at=now)
    quality_items = qualities if qualities is not None else data.get("quality", [])
    for quality in _list(quality_items):
        if not isinstance(quality, dict):
            raise ProviderError("Invalid OpenML dataset quality metadata")
        if quality.get("name") == "NumberOfInstances":
            b["sample_count"] = _number(quality.get("value"))
    protocol = {"dataset_id": did, "dataset_version": b["dataset_revision"],
                "target_feature": _text(data.get("default_target_attribute")),
                "md5_checksum": _text(data.get("md5_checksum"))}
    task_fields = set()
    if task:
        b["task_type"] = _text(task.get("task_type"))
        protocol["task_id"] = tid
        inputs = _inputs(task)
        source = inputs.get("source_data", {}).get("data_set", {})
        if not isinstance(source, dict) or _id(source.get("data_set_id")) != did:
            raise ProviderError("OpenML task references a different dataset")
        protocol["target_feature"] = _text(source.get("target_feature")) or protocol["target_feature"]
        estimation = inputs.get("estimation_procedure", {}).get("estimation_procedure", {})
        if isinstance(estimation, dict):
            parameters = {p["name"]: p.get("value") for p in _list(estimation.get("parameter")) if isinstance(p, dict) and isinstance(p.get("name"), str)}
            protocol.update(estimation_procedure_id=_text(estimation.get("id")),
                            estimation_procedure_type=_text(estimation.get("type")),
                            data_splits_url=_link(estimation.get("data_splits_url")),
                            number_folds=_number(parameters.get("number_folds")),
                            number_repeats=_number(parameters.get("number_repeats")),
                            estimation_parameters=parameters)
            if protocol["data_splits_url"]:
                if "crossvalidation" in (protocol.get("estimation_procedure_type") or "").lower():
                    folds = protocol.get("number_folds")
                    cv = f"{folds}-fold" if folds else "k-fold"
                    b["train_split"] = f"{cv} cross-validation (official split file, TRAIN rows)"
                    b["test_split"] = f"{cv} cross-validation (official split file, TEST rows per fold; no fixed held-out partition)"
                else:
                    b["train_split"] = "Official task split file (TRAIN rows)"
                    b["test_split"] = "Official task split file (TEST rows)"
        measures = inputs.get("evaluation_measures", {}).get("evaluation_measures", {})
        if isinstance(measures, dict):
            measure = measures.get("evaluation_measure")
            if isinstance(measure, str):
                b["metric_name"] = _text(measure)
            elif isinstance(measure, list) and len(measure) == 1 and isinstance(measure[0], str):
                b["metric_name"] = _text(measure[0])
        task_fields = {"title", "task_type", "evaluation_protocol", "train_split", "test_split", "metric_name"}
    b["evaluation_protocol"] = protocol
    b["provenance"] = {field: {"value": value, "source_provider": "openml" if value is not None else None,
                                      "source_url": (source_url if field in task_fields else dataset_url) if value is not None else None,
                                      "status": "verified" if value is not None else "missing",
                                      "confidence": "high" if value is not None else None}
                       for field, value in b.items() if field not in {"id", "slug", "created_at", "updated_at"}}
    if qualities is not None and b["sample_count"] is not None:
        b["provenance"]["sample_count"]["source_url"] = API + "data/qualities/" + did
    if b["dataset_public"] is True:
        # Detail records explicitly report visibility. Search records omit it,
        # but come from OpenML's active public dataset listing, not arbitrary URLs.
        b["provenance"]["dataset_public"]["source_url"] = (API + "data/" + did if data.get("visibility") == "public" else API + "data/list/status/active")
    checks = {"dataset_url": b["dataset_public"] is True,
              "metric_name": bool(b["metric_name"]), "published_score": False,
              "official_split": bool(protocol.get("data_splits_url")), "repository_url": False, "evaluation_script": False}
    missing = [key for key, value in checks.items() if not value]
    b.update(sources=[{"provider": "openml", "external_id": external_id, "external_url": source_url, "last_synced_at": now}], results=[],
             readiness={"status": "partial", "score": 6 - len(missing), "total": 6, "missing": missing},
             compatibility={"executable": False, "executor": None, "reasons": ["OpenML tasks require a supported executor adapter."],
                            "comparability": "No published result selected; task split definitions alone do not establish a comparable run."})
    # Dataset references live in field provenance and protocol. Do not register
    # d/ID as a task's identity source: tasks sharing data have distinct splits.
    return b


class OpenMLProvider:
    name = "openml"

    def _get(self, path):
        # API keys appear only in the request. Provenance always uses clean URLs.
        token = credential("OPENML_API_KEY")
        url = API + path + ("?" + urlencode({"api_key": token}) if token else "")
        raw = safe_json(url)
        if not isinstance(raw, dict) or "error" in raw:
            raise ProviderError("OpenML response unavailable or invalid")
        return raw

    def get_benchmark(self, identifier: str) -> dict:
        if not isinstance(identifier, str) or not re.fullmatch(r"[dt]/[1-9][0-9]{0,9}", identifier):
            raise ProviderError("Invalid OpenML identifier; use d/ID or t/ID")
        kind, numeric = identifier.split("/")
        task = None
        did = numeric
        if kind == "t":
            task = self._get("task/" + numeric).get("task")
            if not isinstance(task, dict) or _id(task.get("task_id")) != numeric:
                raise ProviderError("Invalid OpenML task metadata")
            inputs = _inputs(task)
            source = inputs.get("source_data", {}).get("data_set", {})
            if not isinstance(source, dict):
                raise ProviderError("Invalid OpenML task metadata")
            did = _id(source.get("data_set_id"))
        data = self._get("data/" + did).get("data_set_description")
        if not isinstance(data, dict) or _id(data.get("id")) != did:
            raise ProviderError("Invalid OpenML dataset metadata")
        # Qualities are supplementary: an outage does not discard valid metadata.
        qualities = None
        try:
            quality_response = self._get("data/qualities/" + did).get("data_qualities", {})
            if isinstance(quality_response, dict):
                qualities = _list(quality_response.get("quality"))
        except ProviderError:
            pass
        return normalize_openml(data, task, qualities)

    def search(self, query: str = "", limit: int = 10) -> list[dict]:
        if not isinstance(query, str) or len(query) > 200 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProviderError("Invalid OpenML search parameters")
        # One bounded request; OpenML data_name is a provider-side name filter.
        if query.strip() and not re.fullmatch(r"[A-Za-z0-9_. -]+", query.strip()):
            raise ProviderError("OpenML search supports dataset names")
        path = "data/list/" + ("data_name/" + quote(query.strip(), safe="") + "/" if query.strip() else "")
        raw = self._get(path + "limit/" + str(limit) + "/status/active")
        data = raw.get("data", {})
        rows = data.get("dataset") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ProviderError("Invalid OpenML search response")
        unique = {}
        for row in rows[:limit]:
            if isinstance(row, dict) and row.get("status") == "active":
                benchmark = normalize_openml(row)
                unique[benchmark["id"]] = benchmark
        return list(unique.values())
