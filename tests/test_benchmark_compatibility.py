import pytest

from wildfire_researcher.benchmarks.compatibility import (
    EXECUTION_FIELDS, compatibility, readiness, wildfire_benchmark,
)


def test_pinned_seed_complete_but_validation_not_test_comparable():
    benchmark = wildfire_benchmark()
    assert benchmark["readiness"] == {"status": "complete", "score": 6, "total": 6, "missing": []}
    assert benchmark["compatibility"]["executable"]
    assert "cannot be compared" in benchmark["compatibility"]["comparability"]
    assert benchmark["publication_date"] is None
    assert benchmark["license"] == "other"
    assert benchmark["results"][0]["dataset_revision"] == benchmark["dataset_revision"]


@pytest.mark.parametrize("field", EXECUTION_FIELDS)
def test_every_execution_field_is_checked_even_with_rewritten_provenance(field):
    benchmark = wildfire_benchmark()
    benchmark[field] = "altered"
    benchmark["provenance"][field]["value"] = "altered"
    assert not compatibility(benchmark)["executable"]


@pytest.mark.parametrize("field", list(wildfire_benchmark()["evaluation_protocol"]))
def test_every_protocol_property_checked(field):
    benchmark = wildfire_benchmark()
    benchmark["evaluation_protocol"][field] = None if benchmark["evaluation_protocol"][field] is not None else []
    assert not compatibility(benchmark)["executable"]


def test_user_edited_original_value_does_not_regain_source_verification():
    benchmark = wildfire_benchmark()
    benchmark["provenance"]["published_score"]["status"] = "user_edited"
    assert not compatibility(benchmark)["executable"]


def test_identity_and_source_are_not_inferred_from_dataset_name():
    benchmark = wildfire_benchmark()
    benchmark["source"] = "huggingface"
    benchmark["id"] = "imported-dataset"
    assert not compatibility(benchmark)["executable"]
    benchmark = wildfire_benchmark()
    benchmark["sources"][0]["external_id"] = "attacker/WildfireIA"
    assert not compatibility(benchmark)["executable"]


def test_extra_protocol_key_and_changed_reference_result_block_execution():
    benchmark = wildfire_benchmark()
    benchmark["evaluation_protocol"]["target_column"] = "arbitrary"
    assert not compatibility(benchmark)["executable"]
    benchmark = wildfire_benchmark()
    benchmark["results"][0]["split"] = "validation"
    assert not compatibility(benchmark)["executable"]


def test_informational_edits_and_refresh_timestamps_do_not_change_protocol():
    benchmark = wildfire_benchmark()
    benchmark["title"] = "My wildfire experiment"
    benchmark["sources"][0]["last_synced_at"] = "later"
    assert compatibility(benchmark)["executable"]


def test_metadata_completeness_is_independent_and_zero_is_present():
    benchmark = wildfire_benchmark()
    benchmark["id"] = "unsupported"
    benchmark["published_score"] = 0
    assert readiness(benchmark)["status"] == "complete"
    assert not compatibility(benchmark)["executable"]
    benchmark["evaluation_protocol"] = {}
    assert readiness(benchmark)["missing"] == ["splits", "evaluation_script"]
    assert readiness({})["score"] == 0


def test_readiness_requires_reproducible_splits_and_evaluation_script():
    benchmark = wildfire_benchmark()
    benchmark["validation_split"] = None
    del benchmark["evaluation_protocol"]["evaluation_script"]
    assert readiness(benchmark)["missing"] == ["splits", "evaluation_script"]


def test_no_shared_mutable_seed_state():
    first = wildfire_benchmark()
    first["evaluation_protocol"]["split_years"]["train"].clear()
    assert compatibility(wildfire_benchmark())["executable"]


def test_bad_provenance_and_sources_fail_closed():
    for field in ("provenance", "sources"):
        benchmark = wildfire_benchmark()
        benchmark[field] = None
        assert not compatibility(benchmark)["executable"]


@pytest.mark.parametrize("access", [None, False, "true", 1])
def test_readiness_requires_explicit_public_access(access):
    benchmark = wildfire_benchmark()
    benchmark["dataset_public"] = access
    benchmark["repository_public"] = access
    assert readiness(benchmark)["missing"] == ["dataset_url", "repository_url"]


def test_task_split_file_can_establish_reproducibility_without_validation_split():
    benchmark = {"evaluation_protocol": {"data_splits_url": "https://www.openml.org/api_splits/get/1/Task_1_splits.arff"}}
    assert "splits" not in readiness(benchmark)["missing"]


def test_descriptive_split_recipe_does_not_establish_reproducibility():
    benchmark = {"train_split": "80%", "validation_split": "10%", "test_split": "10%"}
    assert "splits" in readiness(benchmark)["missing"]
    benchmark["evaluation_protocol"] = {"data_splits_url": "   "}
    assert "splits" in readiness(benchmark)["missing"]


def test_canonical_public_access_has_pinned_provenance():
    benchmark = wildfire_benchmark()
    for field in ("dataset_public", "repository_public"):
        assert benchmark[field] is True
        assert benchmark["provenance"][field]["status"] == "verified"
        assert "/blob/" in benchmark["provenance"][field]["source_url"]
