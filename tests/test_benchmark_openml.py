import copy
import json

import pytest

from wildfire_researcher.benchmarks import openml as o
from wildfire_researcher.benchmarks.providers import ProviderError


DATA = {"id": "15", "name": "breast-w", "version": "1", "licence": "Public", "default_target_attribute": "Class", "visibility": "public", "upload_date": "2014-01-01"}
TASK = {"task_id": "15", "task_name": "Task 15: breast-w", "task_type": "Supervised Classification", "input": [
    {"name": "source_data", "data_set": {"data_set_id": "15", "target_feature": "Class"}},
    {"name": "estimation_procedure", "estimation_procedure": {"id": "1", "type": "crossvalidation", "data_splits_url": "https://openml.org/api_splits/get/15/Task_15_splits.arff", "parameter": [{"name": "number_folds", "value": "10"}, {"name": "number_repeats", "value": "1"}]}},
    {"name": "evaluation_measures", "evaluation_measures": {"evaluation_measure": []}}]}


def test_task_protocol_and_missing_metrics():
    b = o.normalize_openml(DATA, TASK, [{"name": "NumberOfInstances", "value": "699.0"}])
    assert b["id"] == "openml-t-15"
    assert b["dataset_identifier"] == "d/15"
    assert b["sample_count"] == 699
    assert b["metric_name"] is None
    assert b["metric_direction"] is None
    assert b["published_score"] is None
    assert b["publication_date"] is None
    assert b["evaluation_protocol"]["target_feature"] == "Class"
    assert b["evaluation_protocol"]["number_folds"] == 10
    assert b["evaluation_protocol"]["number_repeats"] == 1
    assert b["validation_split"] is None
    assert not b["compatibility"]["executable"]
    assert b["provenance"]["evaluation_protocol"]["source_url"] == "https://www.openml.org/t/15"


def test_dataset_and_task_distinct():
    dataset = o.normalize_openml(DATA)
    task = o.normalize_openml(DATA, TASK)
    assert dataset["id"] != task["id"]
    assert dataset["dataset_identifier"] == task["dataset_identifier"]
    assert dataset["task_type"] is None
    assert dataset["train_split"] is None
    assert {s["external_id"] for s in task["sources"]} == {"t/15"}
    assert {s["external_id"] for s in dataset["sources"]} == {"d/15"}


def test_tasks_sharing_data_never_share_identity_source():
    other_task = {**TASK, "task_id": "100"}
    first = o.normalize_openml(DATA, TASK)
    second = o.normalize_openml(DATA, other_task)
    assert first["id"] != second["id"]
    assert first["sources"][0]["external_id"] != second["sources"][0]["external_id"]


def test_malformed_quality_is_sanitized():
    with pytest.raises(ProviderError, match="Invalid OpenML dataset quality metadata"):
        o.normalize_openml(DATA, qualities=[None])


def test_malformed_task_input_is_sanitized():
    task = {**TASK, "input": [{"name": []}]}
    with pytest.raises(ProviderError, match="Invalid OpenML task metadata"):
        o.normalize_openml(DATA, task)


def test_no_metric_selection_among_multiple():
    task = copy.deepcopy(TASK)
    task["input"][-1]["evaluation_measures"]["evaluation_measure"] = ["auc", "accuracy"]
    assert o.normalize_openml(DATA, task)["metric_name"] is None


def test_single_explicit_metric_preserved():
    task = copy.deepcopy(TASK)
    task["input"][-1]["evaluation_measures"]["evaluation_measure"] = ["area_under_roc_curve"]
    b = o.normalize_openml(DATA, task)
    assert b["metric_name"] == "area_under_roc_curve"
    assert b["metric_direction"] is None


def test_mismatched_dataset_rejected():
    task = copy.deepcopy(TASK)
    task["input"][0]["data_set"]["data_set_id"] = "61"
    with pytest.raises(ProviderError):
        o.normalize_openml(DATA, task)


@pytest.mark.parametrize("identifier", ["15", "d/0", "t/-1", "d/15?api_key=secret", "d/../15", "d/15/extra", "https://openml.org/d/15", None])
def test_identifiers(identifier):
    with pytest.raises(ProviderError):
        o.OpenMLProvider().get_benchmark(identifier)


def test_live_request_paths_keys_not_retained(monkeypatch):
    paths = []
    def fetch(url):
        paths.append(url)
        if "/task/" in url:
            return {"task": TASK}
        if "/qualities/" in url:
            return {"data_qualities": {"quality": [{"name": "NumberOfInstances", "value": "699"}]}}
        return {"data_set_description": DATA}
    monkeypatch.setattr(o, "safe_json", fetch)
    monkeypatch.setattr(o, "credential", lambda name: "SENSITIVE_TEST_TOKEN")
    b = o.OpenMLProvider().get_benchmark("t/15")
    assert len(paths) == 3
    assert all(url.endswith("?api_key=SENSITIVE_TEST_TOKEN") for url in paths)
    assert "SENSITIVE_TEST_TOKEN" not in json.dumps(b)
    assert "api_key" not in json.dumps(b)


def test_quality_outage_returns_partial(monkeypatch):
    def get(path):
        if "qualities" in path:
            raise ProviderError("Provider is unavailable")
        return {"data_set_description": DATA}
    provider = o.OpenMLProvider()
    monkeypatch.setattr(provider, "_get", get)
    b = provider.get_benchmark("d/15")
    assert b["sample_count"] is None
    assert b["readiness"]["status"] == "partial"


def test_search_one_bounded_request_deduplicates(monkeypatch):
    paths = []
    def get(path):
        paths.append(path)
        return {"data": {"dataset": [{"did": 61, "name": "iris", "status": "active"}] * 3}}
    provider = o.OpenMLProvider()
    monkeypatch.setattr(provider, "_get", get)
    result = provider.search("iris", 2)
    assert len(result) == 1
    assert paths == ["data/list/data_name/iris/limit/2/status/active"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-3", "3.5", None, []])
def test_invalid_counts_stay_missing(value):
    assert o.normalize_openml(DATA, qualities=[{"name": "NumberOfInstances", "value": value}])["sample_count"] is None


def test_source_url_credentials_rejected():
    data = {**DATA, "paper_url": "https://secret@example.org/paper"}
    assert o.normalize_openml(data)["paper_url"] is None


def test_provider_error_body_is_not_exposed(monkeypatch):
    monkeypatch.setattr(o, "safe_json", lambda url: {"error": {"message": "SECRET"}})
    monkeypatch.setattr(o, "credential", lambda name: None)
    with pytest.raises(ProviderError, match="^OpenML response unavailable or invalid$"):
        o.OpenMLProvider().get_benchmark("d/15")


@pytest.mark.parametrize("data,expected", [({"id": "15"}, None), ({"id": "15", "visibility": "public"}, True), ({"id": "15", "status": "active"}, True), ({"id": "15", "status": "deactivated"}, None)])
def test_public_access_has_provenance(data, expected):
    b = o.normalize_openml(data)
    assert b["dataset_public"] is expected
    assert b["repository_public"] is None
    assert b["provenance"]["dataset_public"]["status"] == ("verified" if expected is True else "missing")
    assert b["provenance"]["repository_public"]["status"] == "missing"
    assert ("dataset_url" not in b["readiness"]["missing"]) is (expected is True)
