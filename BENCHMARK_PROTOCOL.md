# Benchmark protocol (verified against the pinned official implementation)

**Current implementation update:** [AUDIT_FIXES.md](AUDIT_FIXES.md) supersedes the
earlier certification and test-isolation claims below. Immutable freezes, fixed
seeds and dataset/cache hashes are now enforced. Historical results remain
exploratory evidence; unknown paper seeds and prior test disclosure still apply.

Everything below was read from the official code and manifests, not from the paper text.

| Item | Value | Source |
|---|---|---|
| Repository | https://github.com/LabRAI/WildfireIA, commit `aba9be9ef046a03e868a61c4139aa5bfcd7b5b56` (2026-06-18) | `WildfireIA/` clone, `protocol.PINNED_COMMIT` |
| Dataset | `WildfireIA/Anonymous-WildfireIA` on Hugging Face, revision `cd1fcad871c4293ec7bf066229d8714f059d42de` | `WildfireIA/data/HF_REVISION.txt` |
| Task | `ia_failure`: binary initial-attack failure per FPA-FOD natural wildfire event | `label_manifest_natural.json` |
| Label | 0 if final size <= 10 ha, 1 if >= 50 ha, events between 10 and 50 ha are excluded | `label_manifest_natural.json`, `dataloader.filter_task_samples` |
| Cohort | 38,128 events; 35,791 labelled: train 22,576 / val 7,047 / test 6,168 | measured from `master_features_natural_2016_2020.parquet` |
| Split | chronological: train 2016–2018, validation 2019, test 2020; the `split` column is shipped in the master table | `dataloader.split_years`, `split_frames` |
| Positives | train 1,704 (7.55%), val 428 (6.07%), test 513 (8.32%) | measured |
| Prediction time | discovery day D. Weather aggregates cover D-4..D; VIIRS thermal features are day-D only | `temporal_protocol_manifest_natural.json` |
| Forbidden predictors | `fire_size_acres, fire_size_ha, ia_failure_label, contain_dt, containment_hours, log_containment_hours, log_fire_size_ha, FIRE_SIZE, FIRE_SIZE_CLASS, CONT_DATE, CONT_TIME, MTBS_ID, MTBS_FIRE_NAME` | `feature_manifest_natural.json["forbidden_as_features"]`, removed in `requested_feature_columns` |
| Feature protocols | the 21 documented `--input_protocol` values (metadata, firms, weather, fuel, vegetation, topography, access, human, metadata_<source> x5, all, all_without_<source> x7) | README + `dataloader.PROTOCOL_GROUPS` |
| Preprocessing | numeric: train-median imputation then `StandardScaler` fit on train only; categoricals one-hot fit on train, val/test re-indexed | `dataloader.fit_transform_event_features` |
| Metric | `sklearn.metrics.average_precision_score` on raw scores (AP, not trapezoidal PR area) plus AUROC, F1/precision/recall at the best-F1 validation threshold, Brier, ECE, precision/recall@k | `train.classification_metrics`, `best_f1_threshold` |
| Published result | XGBoost, full input, 5 weather days: **0.533 test AUPRC, mean over five seeds** | official project page |
| Official XGBoost | n_estimators 1000, learning_rate 0.03, max_depth 4, subsample 0.8, colsample_bytree 0.8, hist, eval_metric aucpr, scale_pos_weight = neg/pos, early stopping 50 rounds on the validation split | `train.build_xgboost_model`, `fit_xgboost_with_fallback` |
| Official logistic regression | class_weight balanced, C 1.0, lbfgs, max_iter 5000 | `train.train_logistic_or_ridge` |
| Seeds | the repository names only seed 553371; the five seeds behind 0.533 are not published | README, docs |

## How this project uses the protocol

- The official `dataloader.py` builds every cache we train on (`protocol.ensure_tabular_cache` calls `build_tabular_cache`), so split, label, leakage removal and preprocessing are the official ones. Only the event-level canonical tables (~40 MB) are needed for tabular caches; the 2.4 GB patch tables are for spatial models and are not downloaded.
- The official `train.py` metric code (`classification_metrics`, `best_f1_threshold`) scores every experiment (`protocol.classification_metrics`).
- The research loop trains on 2016–2018 and scores 2019 only. `protocol.load_research_splits` drops the test split before returning; the research state, the W&B run config and the UI never contain test numbers. ARIA never sees 2020.
- Research runs use seed 553371 (the only published seed). Scores are labelled `VALIDATION_AUPRC`. A subsampled development run is labelled `DEV_SCORE` and can never be compared.
- After the budget is exhausted ARIA recommends one experiment to freeze. `final_eval.evaluate_frozen` trains that configuration on train (early stopping on 2019 as the official script does) for five seeds `553371..553375`, scores 2020 once per seed with the official metric code, and reports mean ± std. The backend sets `benchmark_beaten` only if the run is protocol-matched (official cohort, no subsampling, pinned code) and the mean test AUPRC is strictly greater than 0.533. The frontend displays that flag; it never computes it.
- `firms` protocol restricts the sample to VIIRS-matched events, so it is marked not comparable.

## Deviations and caveats to state with any claim

1. **Seeds.** The official five-seed list is not public. Our five seeds are ours; the published number could move with different seeds. We report our std (0.0024 in session `wf-20260913-live1`).
2. **Early stopping on xgboost 3.x.** The official `train.py` passes `early_stopping_rounds` to `fit()`, which raises `TypeError` on xgboost >= 2 and silently falls back to *no* early stopping (`xgboost_fit_note: no_early_stopping_api`). Our runner passes it to the constructor so the intended 50-round early stopping happens. Measured on this machine, seed 553371, depth 4, full input: official script (no early stopping) val 0.4848 / test 0.5285; our runner (early stopping, best iteration 459) val 0.4830. Both are the same protocol; the difference is the early-stopping behaviour the official script intended.
3. **Validation vs test.** The 2019 validation year has a lower positive rate (6.1%) than the 2020 test year (8.3%), so validation AUPRC is systematically lower than test AUPRC for the same model. Validation numbers must not be compared with 0.533.
4. **Threshold-dependent metrics** (precision, recall, F1) use the best-F1 validation threshold and are reported for error analysis only; AUPRC is threshold-free.
5. The final evaluation is run once per session for the single configuration ARIA recommends. Candidates are never scored on the test year during the loop.

## Verification performed

- `tests/test_protocol.py`: split years, cohort sizes, forbidden columns absent from every cache, train-only preprocessing, AP-vs-trapezoid parity, degenerate labels and NaN scores rejected.
- `tests/test_official_parity.py`: runs the pinned `train.py` (logistic regression, metadata protocol, seed 553371) and matches our runner's validation AUPRC/AUROC to 2e-3.
- Manual: official `train.py` XGBoost full-input run for seed 553371 (`WildfireIA/experiments/ia_failure/full/tabular/weather5_all/xgboost_seed553371/metrics.json`).
# Current safeguards

See [AUDIT_FIXES.md](AUDIT_FIXES.md). The implementation now enforces immutable
evaluation identity, fixed seeds and data/cache hash verification. Historical
`benchmark_beaten` flags described below are preserved evidence, not current UI
certification. Prior test disclosure and unknown paper seeds remain limitations.
