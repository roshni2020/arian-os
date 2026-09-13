"""Catalog metadata and the closed, pinned WildfireIA execution boundary.

This module does no network access, dataset loading, training or test evaluation.
The service must keep identity/source/provenance fields server-owned: this is a
protocol allowlist, not authentication for arbitrary client-supplied records.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any

from .. import protocol

REPO = protocol.PINNED_REPO_URL
COMMIT = protocol.PINNED_COMMIT
REPO_PIN = f"{REPO}/tree/{COMMIT}"
README = f"{REPO}/blob/{COMMIT}/README.md"
RESULT_SOURCE = f"{REPO}/blob/{COMMIT}/docs/index.html"
CODE_SOURCE = f"{REPO}/blob/{COMMIT}/dataloader.py"
METRIC_SOURCE = f"{REPO}/blob/{COMMIT}/train.py"
DATASET_URL = f"https://huggingface.co/datasets/{protocol.DATASET_REPO}"
DATASET_PIN = f"{DATASET_URL}/tree/{protocol.DATASET_REVISION}"
DATASET_CARD = f"{DATASET_URL}/blob/{protocol.DATASET_REVISION}/README.md"
METRIC_DEFINITION = "sklearn.metrics.average_precision_score on raw scores (official classification_metrics)"
READINESS_FIELDS = (
    "dataset_url", "metric_name", "published_score", "splits",
    "repository_url", "evaluation_script",
)
EXECUTION_FIELDS = (
    "id", "slug", "source", "task_type", "repository_url", "dataset_url",
    "dataset_provider", "dataset_identifier", "dataset_revision", "metric_name",
    "metric_direction", "published_score", "published_model", "train_split",
    "validation_split", "test_split", "evaluation_protocol", "leakage_notes", "results",
)
COMPARABILITY = (
    "Validation AUPRC guides research only and cannot be compared to the published "
    "0.533 held-out test reference. The published five-seed list is not fully disclosed; "
    "existing frozen final-evaluation gates remain required."
)


def readiness(benchmark: dict[str, Any]) -> dict[str, Any]:
    """Six metadata fields; completeness never grants an executor."""
    evaluation = benchmark.get("evaluation_protocol")
    evaluation = evaluation if isinstance(evaluation, dict) else {}
    present = {field: benchmark.get(field) for field in READINESS_FIELDS}
    present["dataset_url"] = bool(benchmark.get("dataset_url")) and benchmark.get("dataset_public") is True
    present["repository_url"] = bool(benchmark.get("repository_url")) and benchmark.get("repository_public") is True
    canonical_splits = (
        benchmark.get("train_split") == "2016-2018"
        and benchmark.get("validation_split") == "2019"
        and benchmark.get("test_split") == "2020"
        and evaluation.get("split_years") == protocol.SPLIT_YEARS
        and benchmark.get("dataset_identifier") == protocol.DATASET_REPO
        and benchmark.get("dataset_revision") == protocol.DATASET_REVISION
    )
    split_url = evaluation.get("data_splits_url")
    present["splits"] = canonical_splits or (isinstance(split_url, str) and bool(split_url.strip()))
    present["evaluation_script"] = evaluation.get("evaluation_script")
    missing = [field for field in READINESS_FIELDS
               if present[field] is None or present[field] == ""
               or present[field] == {} or present[field] == []
               or (field in {"dataset_url", "repository_url", "splits"} and not present[field])]
    return {"status": "partial" if missing else "complete", "score": 6 - len(missing),
            "total": 6, "missing": missing}


def _canonical() -> dict[str, Any]:
    evaluation = {
        "repository_commit": COMMIT,
        "task": protocol.TASK,
        "representation": protocol.REPRESENTATION,
        "split_years": deepcopy(protocol.SPLIT_YEARS),
        "label_rule": protocol.LABEL_RULE,
        "prediction_time": protocol.PREDICTION_TIME,
        "metric_definition": METRIC_DEFINITION,
        "evaluation_script": METRIC_SOURCE,
        "input_protocol": "all",
        "weather_days": 5,
        "standardize": True,
        "research_split": "val",
        "reference_split": "test",
        "published_seed_count": 5,
        "published_seeds": None,
        "documented_seed": protocol.PUBLISHED_SEED,
        "forbidden_features": "All forbidden_as_features entries in the pinned feature_manifest_natural.json",
        "preprocessing": "Official dataloader.py; preprocessing fitted on training split only",
        "final_evaluation": "Existing frozen final-evaluation gate only; never during validation research",
    }
    fields = {
        "id": "wildfireia", "slug": "wildfireia", "title": "WildfireIA",
        "description": "Predict initial attack failure from discovery-time public environmental data for naturally caused US wildfire events.",
        "domain": "wildfire", "task_type": "ia_failure", "publication_date": None,
        "paper_url": f"{REPO}/blob/{COMMIT}/docs/assets/wildfireia-paper.pdf",
        "repository_url": REPO, "dataset_url": DATASET_URL,
        "dataset_public": True, "repository_public": True,
        "dataset_provider": "huggingface", "dataset_identifier": protocol.DATASET_REPO,
        "dataset_revision": protocol.DATASET_REVISION, "metric_name": "AUPRC",
        "metric_direction": "maximize", "published_score": protocol.PUBLISHED_TEST_AUPRC,
        "published_model": protocol.PUBLISHED_MODEL,
        # This is the event backbone, not the filtered supervised Task 1 count.
        "sample_count": 38128, "license": "other",
        "train_split": "2016-2018", "validation_split": "2019", "test_split": "2020",
        "evaluation_protocol": evaluation,
        "leakage_notes": "Discovery-day inputs only; exclude target-derived and post-discovery columns listed by the pinned feature manifest. Events strictly between 10 and 50 ha are excluded. 38,128 is the event backbone count, not the filtered Task 1 sample count.",
        "source": "curated",
        "results": [{"id": "wildfireia-xgboost-test-five-seeds", "model": protocol.PUBLISHED_MODEL,
                     "metric_name": "AUPRC", "metric_direction": "maximize",
                     "metric_definition": METRIC_DEFINITION, "score": protocol.PUBLISHED_TEST_AUPRC,
                     "dataset_identifier": protocol.DATASET_REPO,
                     "dataset_revision": protocol.DATASET_REVISION, "split": "test (2020)",
                     "source_url": RESULT_SOURCE}],
    }
    evidence = {key: ("github", README) for key in fields}
    for key in ("dataset_provider", "dataset_identifier", "dataset_url", "dataset_revision", "dataset_public", "license"):
        evidence[key] = ("huggingface", DATASET_CARD)
    for key in ("published_score", "published_model", "results"):
        evidence[key] = ("github", RESULT_SOURCE)
    for key in ("train_split", "validation_split", "test_split", "evaluation_protocol", "leakage_notes"):
        evidence[key] = ("github", CODE_SOURCE)
    for key in ("metric_name", "metric_direction"):
        evidence[key] = ("github", METRIC_SOURCE)
    local_fields = {"id", "slug", "source"}
    fields["provenance"] = {
        key: {"value": deepcopy(value),
              "source_provider": None if value is None or key in local_fields else evidence[key][0],
              "source_url": None if value is None or key in local_fields else evidence[key][1],
              "status": "missing" if value is None else "inferred" if key in local_fields else "verified",
              "confidence": None if value is None else "high"}
        for key, value in fields.items()
    }
    fields["sources"] = [
        {"provider": "github", "external_id": f"LabRAI/WildfireIA@{COMMIT}", "external_url": REPO_PIN},
        {"provider": "huggingface", "external_id": f"{protocol.DATASET_REPO}@{protocol.DATASET_REVISION}", "external_url": DATASET_PIN},
    ]
    return fields


def _same(left: Any, right: Any) -> bool:
    """JSON strict comparison also rejects booleans substituted for integers."""
    try:
        return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return False


def compatibility(benchmark: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on any execution-relevant or trusted-evidence alteration."""
    if benchmark.get("id") != "wildfireia":
        return {"executable": False, "executor": None,
                "reasons": ["No supported executor is available for this benchmark. A reviewed adapter is required."],
                "comparability": "Imported source metadata does not establish execution or benchmark comparability."}
    expected = _canonical()
    reasons = []
    for field in EXECUTION_FIELDS:
        if not _same(benchmark.get(field), expected[field]):
            reasons.append(f"Unsupported or altered {field}; the pinned WildfireIA adapter is required.")
    provenance = benchmark.get("provenance")
    if not isinstance(provenance, dict) or any(
        not _same(provenance.get(field), expected["provenance"][field]) for field in EXECUTION_FIELDS
    ):
        reasons.append("Execution metadata must retain trusted curated field provenance; user edits are not source verification.")
    sources = benchmark.get("sources")
    identifiers = [{key: source.get(key) for key in ("provider", "external_id", "external_url")}
                   for source in sources if isinstance(source, dict)] if isinstance(sources, list) else None
    if not isinstance(sources, list) or len(sources) != len(expected["sources"]) or not _same(identifiers, expected["sources"]):
        reasons.append("Pinned official repository and dataset source identities are required.")
    return {"executable": not reasons, "executor": "wildfireia" if not reasons else None,
            "reasons": reasons, "comparability": COMPARABILITY if not reasons else "Unsupported or altered benchmarks require an adapter and cannot claim protocol-matched results."}


def wildfire_benchmark() -> dict[str, Any]:
    """Return a fresh trusted catalog seed with pinned evidence and no fabricated dates."""
    benchmark = _canonical()
    now = datetime.now(timezone.utc).isoformat()
    benchmark.update(created_at=now, updated_at=now)
    for source in benchmark["sources"]:
        source["last_synced_at"] = now
    benchmark["readiness"] = readiness(benchmark)
    benchmark["compatibility"] = compatibility(benchmark)
    return benchmark
