# Research report

Session: `wf-20260913-190606-4a5b`

Recorded research mode: `connected`. Fallback runs are development-only.

Validation research and any previously recorded official-test results are separated below. Benchmark superiority is not certified.

| Experiment | Model | Features | Validation AP | Decision |
| --- | --- | --- | ---: | --- |
| exp-000 | logistic_regression | metadata | 0.18417067640399878 | KEEP |
| exp-001 | xgboost | all | 0.48606306740555777 | KEEP |

## Recorded configurations

| Experiment | Model | Features | Weather days | Hyperparameters |
| --- | --- | --- | ---: | --- |
| exp-000 | logistic_regression | metadata | 5 | {"C": 1.0, "class_weight": "balanced"} |
| exp-001 | xgboost | all | 5 | {"colsample_bytree": 0.8, "gamma": 0.0, "learning_rate": 0.03, "max_depth": 3, "min_child_weight": 1.0, "n_estimators": 1000, "reg_alpha": 0.0, "reg_lambda": 1.0, "scale_pos_weight": 12.0, "subsample": 0.8} |

## Verification

- `verify-47500795743a45b9ad1ecf2b16bfdea6`: complete; complete seed pairs: 2; mean validation AP change: 0.29357908546584705.
  Sample standard deviation of paired deltas: 0.000586312818198978; range: 0.29316449969620195 to 0.29399367123549214; incomplete: False. These describe seed variation, not a generalization confidence interval.
  Seed 17: baseline AP 0.18417067640399878, candidate AP 0.47816434763949095, delta 0.29399367123549214.
  Seed 42: baseline AP 0.18417067640399878, candidate AP 0.4773351761002007, delta 0.29316449969620195.

## Recorded selection

Highest recorded validation AP: `exp-001`. This ranking is not a verified deployment recommendation.

Discovery experiment budget: 1. Verification has a separate budget.

## Recorded experiment reasoning

Historical controller statements are reproduced as recorded, not independently established explanations. They are report-only and are excluded from research memory and future discovery evidence.

Experiment `exp-000` — recorded controller `baseline_setup`:
- decision_reason: Keep exp-000 as the valid incumbent and comparison baseline because it is the only completed configuration and establishes a measured 2019 validation AUPRC of 0.1841706764.
- decision_learning: Metadata-only logistic regression has useful discrimination (validation AUROC 0.7493607330) but weak positive-class ranking (validation AUPRC 0.1841706764), a train-to-validation AUPRC gap of 0.1433826449, and 269 false negatives, including 18 of 22 California positives.
- next_question: Can the approved full-input XGBoost configuration raise overall validation AUPRC to at least 0.47 while cutting California false negatives to at most 11 without exceeding 20 California false positives?
Experiment `exp-001` — recorded controller `ARIA`:
- decision_reason: KEEP exp-001 as the final configuration because it is the strongest measured validation result: 2019 validation AUPRC increased from 0.1841706764 to 0.4860630674 (+0.3018923909), with 200 false negatives and 326 false positives versus 269 and 638 for exp-000. It met the overall AUPRC target (>=0.47) and California false-positive limit (17 <= 20), although it missed the California sensitivity targets (14 false negatives > 11; recall 0.3636 < 0.50).
- decision_learning: Full-input XGBoost materially improves ranking and error counts over metadata-only logistic regression. VIIRS-match recall rose from 0.2990 to 0.9278 and overall validation AUROC rose from 0.7494 to 0.8866, but the scale_pos_weight=12 configuration did not deliver the hypothesized California recall: it reduced California false negatives only from 18 to 14 while increasing California false positives from 10 to 17. The train-to-validation AUPRC gap remains substantial (0.6741 vs 0.4861).
- next_question: When the frozen exp-001 configuration is evaluated once on the sealed 2020 test year, does its test AUPRC approach or exceed the published 0.533 benchmark without using the test result for further selection?
- proposal_observation: The metadata-only logistic-regression baseline exp-000 achieved 0.1841706764 validation AUPRC versus 0.3275533213 train AUPRC. At its best-F1 threshold it produced 159 TP, 638 FP, 269 FN, and 5,981 TN. Recall was especially low for VIIRS-matched events (29/97 positives detected; recall 0.2989690722) and California (4/22 detected; 18 false negatives; recall 0.1818181818).
- proposal_hypothesis: Changing only scale_pos_weight from 8.0 in the evidenced exp-012 full-input xgboost configuration to 12.0 will yield at most 11 California validation false negatives while retaining an overall val (2019) validation AUPRC of at least 0.47; the hypothesis is falsified if any success criterion fails.
- proposal_expected_result: The reviewed full-input XGBoost configuration should achieve overall 2019 validation AUPRC of at least 0.47 while reducing the California subgroup to at most 11 false negatives (recall at least 0.50) and keeping California false positives at or below 20. Any failed criterion falsifies the hypothesis.
- proposal_reason: The approved error_proposal requires this exact reviewed configuration for the first post-baseline experiment. Although it changes model family and feature protocol together, that broader change is necessary to test whether nonlinear full-input modeling addresses the baseline's low ranking quality and concentrated false negatives; predicted gains are treated only as falsifiable targets, not measurements.

## Limitations

- Validation selection can overfit the validation data.
- Repeated seeds measure seed variation, not generalization to new datasets.
- Recorded controller reasoning and test results are report-only historical evidence, never future discovery context.
- Model paths are recorded references; availability and deployability are not attested.
- Prior test exposure recorded for this session: False.

## Evidence references

- `wf-20260913-190606-4a5b/exp-000` revision `2026-09-13T19:07:50+00:00`
- `wf-20260913-190606-4a5b/exp-001` revision `2026-09-13T19:16:00+00:00`

## Recorded model references

- `exp-000`: `C:\AI\Projects\focus\artifacts\wf-20260913-190606-4a5b\exp-000\model`
- `exp-001`: `C:\AI\Projects\focus\artifacts\wf-20260913-190606-4a5b\exp-001\model`

## Previously recorded official-test evaluation

No recognized official-test result is recorded in this session. No evaluation was requested.
