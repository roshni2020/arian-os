"""Time the reference configurations on the official validation split (development aid)."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wildfire_researcher import experiments as ex  # noqa: E402
from wildfire_researcher import protocol, runner  # noqa: E402

out = Path(__file__).resolve().parents[1] / "data" / "timing_probe"
configs = [
    ("lr_metadata", ex.canonical_experiment(ex.BASELINE_EXPERIMENT)),
    ("xgb_metadata", ex.canonical_experiment({"model": "xgboost", "feature_protocol": "metadata", "weather_days": 5, "hyperparameters": {}})),
    ("lr_all", ex.canonical_experiment({"model": "logistic_regression", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {}})),
    ("xgb_all", ex.canonical_experiment({"model": "xgboost", "feature_protocol": "all", "weather_days": 5, "hyperparameters": {}})),
]
for name, exp in configs:
    t = time.time()
    r = runner.run_experiment(exp, protocol.RESEARCH_SEED, out / name)
    print(json.dumps({"name": name, "val_auprc": round(r["validation_auprc"], 4), "val_auroc": round(r["validation_auroc"], 4), "train_auprc": round(r["train_auprc"], 4), "n_features": r["n_features"], "runtime_s": round(time.time() - t, 1), "fit_notes": r["fit_notes"]}), flush=True)
