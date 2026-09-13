"""Official-protocol integrity: split, leakage exclusion, train-only preprocessing, metric parity.

These tests need the canonical tables under WildfireIA/data (skipped otherwise). They build the
small 'metadata' cache with the official dataloader and never read the test split.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from wildfire_researcher import config, protocol

needs_data = pytest.mark.skipif(not protocol.canonical_ready(), reason="canonical WildfireIA tables not downloaded")


def test_pinned_commit_matches_local_clone():
    local = protocol.repo_commit()
    if local is None:
        pytest.skip("WildfireIA clone not present")
    assert local == protocol.PINNED_COMMIT


@needs_data
def test_metadata_cache_split_years_and_label_rule():
    data = protocol.load_research_splits("metadata", 5)
    assert "test" not in data, "research loader must never expose the test split"
    train_idx, val_idx = data["train"]["index"], data["val"]["index"]
    assert sorted(train_idx["year"].unique().tolist()) == [2016, 2017, 2018]
    assert val_idx["year"].unique().tolist() == [2019]
    assert set(np.unique(data["train"]["y"]).tolist()) <= {0.0, 1.0}
    assert len(data["train"]["y"]) == 22576 and len(data["val"]["y"]) == 7047


@needs_data
def test_forbidden_columns_never_in_features():
    cache = protocol.ensure_tabular_cache("all", 5)
    meta = json.loads((cache / "metadata.json").read_text())
    forbidden = set(protocol.forbidden_columns())
    used = set(meta["source_feature_columns"]) | set(meta["feature_names"])
    assert not (used & forbidden)
    for col in ("fire_size_ha", "containment_hours", "contain_dt", "MTBS_ID", "ia_failure_label"):
        assert col not in used
    assert meta["scaler_policy"].startswith("StandardScaler fit on train")
    assert meta["imputer_policy"].startswith("numeric train median")


@needs_data
def test_metric_parity_with_official_average_precision():
    from sklearn.metrics import average_precision_score, auc, precision_recall_curve

    rng = np.random.default_rng(0)
    y = (rng.random(500) < 0.1).astype(int)
    s = np.clip(rng.random(500) + 0.4 * y, 0, 1)
    metrics, threshold = protocol.classification_metrics(y, s)
    assert metrics["auprc"] == pytest.approx(average_precision_score(y, s))
    p, r, _ = precision_recall_curve(y, s)
    trapezoid = auc(r, p)
    # AP (official) and trapezoidal PR area are different estimators; make sure we report AP.
    assert metrics["auprc"] != pytest.approx(trapezoid, abs=1e-9) or abs(metrics["auprc"] - trapezoid) < 1e-3
    assert 0.0 < threshold < 1.0


@needs_data
def test_degenerate_labels_and_nan_scores_raise():
    with pytest.raises(ValueError):
        protocol.classification_metrics(np.zeros(10, dtype=int), np.linspace(0, 1, 10))
    y = np.array([0, 1] * 5)
    s = np.linspace(0, 1, 10)
    s[3] = np.nan
    with pytest.raises(ValueError):
        protocol.classification_metrics(y, s)


def test_provenance_fields():
    prov = protocol.provenance()
    assert prov["published_test_auprc"] == 0.533
    assert prov["split_years"]["test"] == [2020]
    assert prov["pinned_commit"] == protocol.PINNED_COMMIT
