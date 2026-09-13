"""Parity with the official implementation: run the pinned WildfireIA train.py for a deterministic
configuration (logistic regression, metadata protocol) and compare its validation AUPRC with our
runner on the same cache and seed. Slow (~30s); needs canonical data."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from wildfire_researcher import config, experiments as ex, protocol, runner

needs_data = pytest.mark.skipif(not protocol.canonical_ready(), reason="canonical WildfireIA tables not downloaded")


@needs_data
def test_logistic_metadata_matches_official_train_py(tmp_path, monkeypatch):
    # The official training entry point expects a test partition. Supply a validation
    # mirror solely as that fixture; never load or evaluate the actual held-out year.
    tr = protocol.official().train
    monkeypatch.setattr(sys, 'argv', ['train.py','--base_dir',str(config.WILDFIREIA_DIR),'--task','ia_failure','--representation','tabular','--input_protocol','metadata','--seed',str(protocol.RESEARCH_SEED)])
    args = tr.parse_args()
    data = protocol.load_research_splits('metadata',5)
    data['test'] = data['val']
    tr.train_logistic_or_ridge(args,data,tmp_path,protocol.cache_path('metadata',5),{'device':'cpu'})
    metrics_path = tmp_path/'metrics.json'
    official = json.loads(metrics_path.read_text())
    ours = runner.run_experiment(ex.canonical_experiment(ex.BASELINE_EXPERIMENT), protocol.RESEARCH_SEED, tmp_path)
    assert ours["validation_auprc"] == pytest.approx(official["val_auprc"], abs=2e-3)
    assert ours["validation_auroc"] == pytest.approx(official["val_auroc"], abs=2e-3)
