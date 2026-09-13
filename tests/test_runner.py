"""Real lightweight training on the official metadata cache (validation only)."""
from __future__ import annotations

import numpy as np
import pytest

from wildfire_researcher import experiments as ex
from wildfire_researcher import protocol, runner

needs_data = pytest.mark.skipif(not protocol.canonical_ready(), reason="canonical WildfireIA tables not downloaded")


@needs_data
def test_metadata_logistic_regression_measures_validation_auprc(tmp_path):
    exp = ex.canonical_experiment(ex.BASELINE_EXPERIMENT)
    result = runner.run_experiment(exp, protocol.RESEARCH_SEED, tmp_path)
    assert result["score_kind"] == runner.SCORE_KIND_VALIDATION
    assert result["benchmark_comparable"] is False
    assert 0.0 < result["validation_auprc"] < 1.0
    assert result["val_size"] == 7047 and result["train_size"] == 22576
    assert result["confusion_matrix"]["fn"] + result["confusion_matrix"]["tp"] == result["val_positives"]
    assert (tmp_path / "predictions_val.npz").exists()
    saved = np.load(tmp_path / "predictions_val.npz")
    assert len(saved["y_score"]) == 7047
    assert result["feature_importance"]


@needs_data
def test_subsampled_run_is_labelled_dev_score(tmp_path):
    exp = ex.canonical_experiment(ex.BASELINE_EXPERIMENT)
    result = runner.run_experiment(exp, 1, tmp_path, limit_train_samples=2000)
    assert result["score_kind"] == runner.SCORE_KIND_DEV
    assert result["train_size"] == 2000
