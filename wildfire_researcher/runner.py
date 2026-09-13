"""Local training executor. Trains on the official train split and evaluates on the official
validation split only. It never touches the 2020 test year; see final_eval.py for that.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import config, protocol

SCORE_KIND_VALIDATION = "VALIDATION_AUPRC"  # official split, full training data, not a test score
SCORE_KIND_DEV = "DEV_SCORE"  # subsampled or otherwise reduced; never comparable


def _fit_model(experiment: dict[str, Any], seed: int, X_train, y_train, X_val, y_val) -> tuple[Any, dict[str, Any]]:
    hp = experiment["hyperparameters"]
    notes: dict[str, Any] = {}
    if experiment["model"] == "logistic_regression":
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(C=hp["C"], class_weight=hp["class_weight"], max_iter=5000, solver="lbfgs", random_state=seed)
        model.fit(X_train, y_train)
        notes["solver"] = "lbfgs"
        notes["n_iter"] = int(np.max(model.n_iter_))
        return model, notes
    if experiment["model"] == "xgboost":
        from xgboost import XGBClassifier

        pos = int(np.sum(y_train == 1))
        neg = int(np.sum(y_train == 0))
        spw = float(neg / max(1, pos)) if hp["scale_pos_weight"] == "auto" else float(hp["scale_pos_weight"])
        model = XGBClassifier(
            n_estimators=hp["n_estimators"],
            learning_rate=hp["learning_rate"],
            max_depth=hp["max_depth"],
            subsample=hp["subsample"],
            colsample_bytree=hp["colsample_bytree"],
            min_child_weight=hp["min_child_weight"],
            reg_lambda=hp["reg_lambda"],
            reg_alpha=hp["reg_alpha"],
            gamma=hp["gamma"],
            scale_pos_weight=spw,
            tree_method="hist",
            device="cpu",
            eval_metric="aucpr",
            early_stopping_rounds=50,
            random_state=seed,
            n_jobs=-1,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        notes["scale_pos_weight_effective"] = spw
        notes["best_iteration"] = int(getattr(model, "best_iteration", -1))
        notes["early_stopping"] = "early_stopping_rounds=50 on validation aucpr (official script behaviour)"
        return model, notes
    raise ValueError(f"Unsupported model {experiment['model']}")


def _predict(model: Any, X) -> np.ndarray:
    return np.asarray(model.predict_proba(X)[:, 1], dtype=float)


def _feature_importance(model: Any, experiment: dict[str, Any], feature_names: list[str], top_k: int = 20) -> list[dict[str, Any]]:
    try:
        if experiment["model"] == "logistic_regression":
            coef = np.asarray(model.coef_[0], dtype=float)
            order = np.argsort(-np.abs(coef))[:top_k]
            return [{"feature": feature_names[i] if i < len(feature_names) else f"f{i}", "importance": float(coef[i]), "kind": "standardized_coefficient"} for i in order]
        booster = model.get_booster()
        gain = booster.get_score(importance_type="gain")
        items = sorted(gain.items(), key=lambda kv: -kv[1])[:top_k]
        out = []
        for name, value in items:
            idx = int(name[1:]) if name.startswith("f") and name[1:].isdigit() else -1
            out.append({"feature": feature_names[idx] if 0 <= idx < len(feature_names) else name, "importance": float(value), "kind": "gain"})
        return out
    except Exception:
        return []


def _downsample_curve(precision: np.ndarray, recall: np.ndarray, max_points: int = 200) -> list[dict[str, float]]:
    n = len(precision)
    idx = np.linspace(0, n - 1, num=min(n, max_points)).astype(int)
    return [{"recall": float(recall[i]), "precision": float(precision[i])} for i in idx]


def _group_breakdown(frame: pd.DataFrame, column: str, y: np.ndarray, pred: np.ndarray, min_count: int = 30, top: int = 8) -> list[dict[str, Any]]:
    """Error breakdown by an eligible discovery-time column. Small groups are flagged."""
    if column not in frame.columns:
        return []
    rows = []
    values = frame[column]
    for value, mask in values.groupby(values, observed=True).groups.items():
        m = np.zeros(len(frame), dtype=bool)
        m[np.asarray(list(mask), dtype=int)] = True
        n = int(m.sum())
        pos = int((y[m] == 1).sum())
        fn = int(((pred[m] == 0) & (y[m] == 1)).sum())
        fp = int(((pred[m] == 1) & (y[m] == 0)).sum())
        rows.append({"group": str(value), "count": n, "positives": pos, "false_negatives": fn, "false_positives": fp, "recall": (pos - fn) / pos if pos else None, "small_group": n < min_count})
    rows.sort(key=lambda r: -r["false_negatives"])
    return rows[:top]


def _val_context(index: pd.DataFrame) -> pd.DataFrame:
    """Join eligible discovery-time columns from the master table for error analysis."""
    master_path = config.CANONICAL_DIR / "master_features_natural_2016_2020.parquet"
    cols = ["fire_id", "state", "discovery_month", "has_viirs_detection_1km_D", "erc_day0", "fbfm40_point"]
    master = pd.read_parquet(master_path)
    cols = [c for c in cols if c in master.columns]
    master = master[cols].copy()
    master["fire_id"] = master["fire_id"].astype(str)
    ctx = index[["fire_id"]].astype(str).merge(master, on="fire_id", how="left")
    if "erc_day0" in ctx.columns:
        try:
            ctx["erc_day0_quartile"] = pd.qcut(pd.to_numeric(ctx["erc_day0"], errors="coerce"), 4, labels=["Q1 low", "Q2", "Q3", "Q4 high"])
        except Exception:
            pass
    if "has_viirs_detection_1km_D" in ctx.columns:
        ctx["viirs_detected_day_D"] = pd.to_numeric(ctx["has_viirs_detection_1km_D"], errors="coerce").fillna(0).astype(int).map({0: "no VIIRS match", 1: "VIIRS match"})
    return ctx


def run_experiment(experiment: dict[str, Any], seed: int, out_dir: Path, limit_train_samples: int | None = None) -> dict[str, Any]:
    """Train and evaluate one canonical experiment. Returns a JSON-serializable result."""
    start = time.monotonic()
    data = protocol.load_research_splits(experiment["feature_protocol"], experiment["weather_days"])
    X_train, y_train = data["train"]["X"], data["train"]["y"].astype(int)
    X_val, y_val = data["val"]["X"], data["val"]["y"].astype(int)
    feature_names = data["feature_names"]
    score_kind = SCORE_KIND_VALIDATION
    if limit_train_samples is not None and limit_train_samples < len(y_train):
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(len(y_train), size=int(limit_train_samples), replace=False))
        X_train, y_train = X_train[idx], y_train[idx]
        score_kind = SCORE_KIND_DEV
    if not np.isfinite(X_train).all() or not np.isfinite(X_val).all():
        raise ValueError("Official cache contains non-finite values")

    model, notes = _fit_model(experiment, seed, X_train, y_train, X_val, y_val)
    val_score = _predict(model, X_val)
    train_score = _predict(model, X_train)
    metrics, threshold = protocol.classification_metrics(y_val, val_score)
    train_metrics, _ = protocol.classification_metrics(y_train, train_score)
    pred = (val_score >= threshold).astype(int)
    tp = int(((pred == 1) & (y_val == 1)).sum())
    fp = int(((pred == 1) & (y_val == 0)).sum())
    fn = int(((pred == 0) & (y_val == 1)).sum())
    tn = int(((pred == 0) & (y_val == 0)).sum())

    from sklearn.metrics import precision_recall_curve

    curve_p, curve_r, _ = precision_recall_curve(y_val, val_score)
    ctx = _val_context(data["val"]["index"])
    breakdowns = {
        "by_viirs_detection": _group_breakdown(ctx, "viirs_detected_day_D", y_val, pred),
        "by_erc_quartile": _group_breakdown(ctx, "erc_day0_quartile", y_val, pred),
        "by_discovery_month": _group_breakdown(ctx, "discovery_month", y_val, pred),
        "by_state": _group_breakdown(ctx, "state", y_val, pred),
        "by_fuel_model": _group_breakdown(ctx, "fbfm40_point", y_val, pred),
    }
    runtime = time.monotonic() - start
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / "predictions_val.npz"
    np.savez_compressed(pred_path, fire_id=data["val"]["fire_id"], y_true=y_val, y_score=val_score, threshold=threshold)
    from .model_bundle import save_bundle
    bundle = save_bundle(model, experiment, seed, data, out_dir, metrics['auprc'])

    result = {
        "score_kind": score_kind,
        "benchmark_comparable": False,  # validation scores are never compared with the published test score
        "split": "val (2019)",
        "validation_auprc": metrics["auprc"],
        "validation_auroc": metrics["auroc"],
        "validation_metrics": metrics,
        "train_auprc": train_metrics["auprc"],
        "threshold_best_f1": threshold,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "false_negative_count": fn,
        "false_positive_count": fp,
        "val_positives": int((y_val == 1).sum()),
        "val_size": int(len(y_val)),
        "train_size": int(len(y_train)),
        "train_positive_rate": float(np.mean(y_train)),
        "n_features": int(X_train.shape[1]),
        "pr_curve": _downsample_curve(curve_p, curve_r),
        "feature_importance": _feature_importance(model, experiment, feature_names),
        "error_breakdowns": breakdowns,
        "fit_notes": notes,
        "runtime_seconds": float(runtime),
        "seed": int(seed),
        "cache_dir": str(data["cache_dir"]),
        "predictions_path": str(pred_path),
        "model_bundle_path": str(bundle),
    }
    return result
