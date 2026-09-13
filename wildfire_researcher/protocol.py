"""Bindings to the official WildfireIA protocol (pinned repository revision).

Everything that defines the benchmark (split, label, forbidden columns, preprocessing,
feature protocols, metrics) is imported from the pinned official code rather than
re-implemented, so results are computed the way the published benchmark computes them.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from . import config

PINNED_REPO_URL = "https://github.com/LabRAI/WildfireIA"
PINNED_COMMIT = "aba9be9ef046a03e868a61c4139aa5bfcd7b5b56"
DATASET_REPO = "WildfireIA/Anonymous-WildfireIA"
DATASET_REVISION = "cd1fcad871c4293ec7bf066229d8714f059d42de"

TASK = "ia_failure"
REPRESENTATION = "tabular"
PUBLISHED_TEST_AUPRC = 0.533
PUBLISHED_MODEL = "xgboost, full input protocol, 5 weather days, mean over five seeds"
PUBLISHED_SEED = 553371  # the only seed named in the official repository
# The official repository names one seed; the five-seed list behind 0.533 is not published.
# We therefore evaluate five documented seeds and state that clearly in every report.
FINAL_EVAL_SEEDS = [553371, 553372, 553373, 553374, 553375]
RESEARCH_SEED = PUBLISHED_SEED

SPLIT_YEARS = {"train": [2016, 2017, 2018], "val": [2019], "test": [2020]}
LABEL_RULE = "ia_failure_label: 0 if final fire size <= 10 ha, 1 if >= 50 ha, events between 10 and 50 ha excluded"
PREDICTION_TIME = "discovery day D; weather from D-4..D, VIIRS thermal detections from day D only"

# The 21 input protocols documented in the official README (dataloader also accepts
# internal aliases 'fire' and 'fire_wide', which are not part of the published protocol list).
FEATURE_PROTOCOLS = [
    "metadata", "firms", "weather", "fuel", "vegetation", "topography", "access", "human",
    "metadata_vegetation", "metadata_fuel", "metadata_topography", "metadata_access", "metadata_human",
    "all", "all_without_fire", "all_without_weather", "all_without_vegetation", "all_without_fuel",
    "all_without_topography", "all_without_access", "all_without_human",
]
WEATHER_DAYS = [1, 2, 3, 4, 5]

PROTOCOL_DESCRIPTIONS = {
    "metadata": "FPA-FOD incident metadata only: location, discovery time, cause (9 raw columns; state/county one-hot).",
    "firms": "FIRMS/VIIRS discovery-day thermal features only; restricts samples to events with a VIIRS match (not comparable to other protocols).",
    "weather": "gridMET weather + fire-danger aggregates only (day0, lag1, multi-day means up to weather_days).",
    "fuel": "LANDFIRE fuel (FBFM40, canopy metrics) only.",
    "vegetation": "LANDFIRE existing vegetation type/cover/height only.",
    "topography": "Elevation, slope, aspect only.",
    "access": "OpenStreetMap road distance/density and fire station proximity only.",
    "human": "WorldPop population density only.",
    "metadata_vegetation": "metadata + vegetation.",
    "metadata_fuel": "metadata + fuel.",
    "metadata_topography": "metadata + topography.",
    "metadata_access": "metadata + access.",
    "metadata_human": "metadata + human.",
    "all": "Official full input: metadata + FIRMS + weather + fuel + vegetation + topography + access + human.",
    "all_without_fire": "Full input minus FIRMS/VIIRS.",
    "all_without_weather": "Full input minus weather/fire danger.",
    "all_without_vegetation": "Full input minus vegetation.",
    "all_without_fuel": "Full input minus fuel.",
    "all_without_topography": "Full input minus topography.",
    "all_without_access": "Full input minus access.",
    "all_without_human": "Full input minus population.",
}

_official: dict[str, Any] = {}


def official() -> SimpleNamespace:
    """Import the pinned official modules (dataloader.py, train.py) exactly once."""
    if not _official:
        repo = config.WILDFIREIA_DIR
        if not (repo / "dataloader.py").exists() or not (repo / "train.py").exists():
            raise FileNotFoundError(f"Official WildfireIA code not found under {repo}")
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        _official["dataloader"] = importlib.import_module("dataloader")
        _official["train"] = importlib.import_module("train")
    return SimpleNamespace(**_official)


def repo_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.WILDFIREIA_DIR, capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or None
    except Exception:
        return None


def provenance() -> dict[str, Any]:
    return {
        "repo": PINNED_REPO_URL,
        "pinned_commit": PINNED_COMMIT,
        "local_commit": repo_commit(),
        "dataset": DATASET_REPO,
        "dataset_revision": DATASET_REVISION,
        "task": TASK,
        "representation": REPRESENTATION,
        "split_years": SPLIT_YEARS,
        "label_rule": LABEL_RULE,
        "prediction_time": PREDICTION_TIME,
        "metric": "sklearn.metrics.average_precision_score on raw scores (official classification_metrics)",
        "published_test_auprc": PUBLISHED_TEST_AUPRC,
        "published_model": PUBLISHED_MODEL,
        'trace_link_version':2,
    }


def canonical_ready() -> bool:
    return (config.CANONICAL_DIR / "master_features_natural_2016_2020.parquet").exists() and (
        config.CANONICAL_DIR / "feature_manifest_natural.json"
    ).exists()


def protocol_includes_weather(protocol: str) -> bool:
    return bool(official().dataloader.protocol_includes_weather(protocol))


def forbidden_columns() -> list[str]:
    manifest = json.loads((config.CANONICAL_DIR / "feature_manifest_natural.json").read_text())
    return sorted(set(manifest.get("forbidden_as_features", [])))


def cache_path(protocol: str, weather_days: int) -> Path:
    return config.CACHE_DIR / TASK / REPRESENTATION / f"weather{weather_days}_{protocol}"


def ensure_tabular_cache(protocol: str, weather_days: int = 5, overwrite: bool = False) -> Path:
    """Build (or reuse) the official tabular cache with the official dataloader code."""
    if protocol not in FEATURE_PROTOCOLS:
        raise ValueError(f"Unknown feature protocol: {protocol}")
    if weather_days not in WEATHER_DAYS:
        raise ValueError(f"weather_days must be one of {WEATHER_DAYS}")
    if not canonical_ready():
        raise FileNotFoundError(f"Canonical tables missing under {config.CANONICAL_DIR}; run scripts/setup_wildfireia.py")
    dl = official().dataloader
    args = SimpleNamespace(
        base_dir=config.WILDFIREIA_DIR,
        canonical_dir=config.CANONICAL_DIR,
        output_dir=config.CACHE_DIR,
        task=TASK,
        representation=REPRESENTATION,
        weather_days=weather_days,
        input_protocol=protocol,
        standardize=True,
        overwrite=overwrite,
    )
    paths = dl.canonical_paths(config.CANONICAL_DIR)
    feature_manifest = dl.load_json(paths["feature_manifest"])
    return Path(dl.build_tabular_cache(args, paths, feature_manifest))


def load_research_splits(protocol: str, weather_days: int = 5) -> dict[str, Any]:
    """Load train and validation arrays only. The test split is never returned here."""
    cache = ensure_tabular_cache(protocol, weather_days)
    import pandas as pd
    data = {'cache_dir':str(cache), 'metadata':json.loads((cache/'metadata.json').read_text()),
            'feature_names':json.loads((cache/'feature_names.json').read_text())['feature_names']}
    for split in ('train','val'):
        data[split] = {'X':np.load(cache/f'X_{split}.npy'), 'y':np.load(cache/f'y_{split}.npy'),
          'fire_id':np.load(cache/f'fire_id_{split}.npy',allow_pickle=True).astype(str),
          'index':pd.read_parquet(cache/f'sample_index_{split}.parquet')}
    return data


def load_sealed_test_split(protocol: str, weather_days: int = 5) -> dict[str, Any]:
    """Only the final official evaluation may call this."""
    cache = ensure_tabular_cache(protocol, weather_days)
    return official().train.load_cache(cache, TASK, REPRESENTATION)


def classification_metrics(y_true: np.ndarray, y_score: np.ndarray) -> tuple[dict[str, float], float]:
    """Official metric set at the official F1-selected threshold. Returns (metrics, threshold)."""
    tr = official().train
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score).astype(float)
    if not np.isfinite(y_score).all():
        raise ValueError("Scores contain NaN or infinity")
    if len(np.unique(y_true)) < 2:
        raise ValueError("Degenerate labels: AUPRC undefined with a single class")
    threshold, _ = tr.best_f1_threshold(y_true, y_score)
    metrics = tr.classification_metrics(y_true, y_score, threshold)
    for key in ("auprc", "auroc"):
        if not np.isfinite(metrics[key]):
            raise ValueError(f"Official metric {key} is not finite")
    return {k: float(v) for k, v in metrics.items()}, float(threshold)
