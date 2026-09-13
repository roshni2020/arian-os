# Research report

Session: `wf-20260913-150158-81be`

Recorded research mode: `connected`. Fallback runs are development-only.

Validation research and any previously recorded official-test results are separated below. Benchmark superiority is not certified.

| Experiment | Model | Features | Validation AP | Decision |
| --- | --- | --- | ---: | --- |
| exp-000 | logistic_regression | metadata | 0.18417067640399878 | KEEP |
| exp-001 | logistic_regression | all | 0.39721230867438967 | KEEP |

## Recorded configurations

| Experiment | Model | Features | Weather days | Hyperparameters |
| --- | --- | --- | ---: | --- |
| exp-000 | logistic_regression | metadata | 5 | {"C": 1.0, "class_weight": "balanced"} |
| exp-001 | logistic_regression | all | 5 | {"C": 1.0, "class_weight": "balanced"} |

## Verification

- `verify-51207f7013e045bd85ca60968f3cbd5a`: draft; complete seed pairs: 0; mean validation AP change: None.
  Sample standard deviation of paired deltas: None; range: None to None; incomplete: True. These describe seed variation, not a generalization confidence interval.

## Recorded selection

Highest recorded validation AP: `exp-001`. This ranking is not a verified deployment recommendation.

Discovery experiment budget: 1. Verification has a separate budget.

## Recorded experiment reasoning

Historical controller statements are reproduced as recorded, not independently established explanations. They are report-only and are excluded from research memory and future discovery evidence.

Experiment `exp-000` — recorded controller `baseline_setup`:
- decision_reason: It is the only completed valid experiment and therefore remains the current best validation reference at AUPRC 0.1841706764, despite a substantial train-validation gap and weak positive ranking.
- decision_learning: Metadata-only balanced logistic regression supplies useful signal but generalizes poorly: validation AUPRC is 0.1433826449 below train AUPRC, and thresholded errors are concentrated in high-fire-danger, VIIRS-matched, and specific fuel groups that metadata does not directly encode.
- next_question: Does adding all permitted discovery-time feature families, without changing the model or regularization, produce a material validation-AUPRC gain and reduce the observed environmental-group misses?
Experiment `exp-001` — recorded controller `ARIA`:
- decision_reason: exp-001 is the strongest valid configuration and should be frozen: its 2019 validation AUPRC was 0.3972123087, a +0.2130416323 absolute gain over the 0.1841706764 metadata-only baseline and well above the prespecified 0.2141706764 success threshold. At the selected best-F1 threshold it also reduced false positives from 638 to 240 while slightly reducing false negatives from 269 to 262. The published 0.533 test benchmark is not used in this decision because it is not comparable to validation scores.
- decision_learning: Adding the full permitted discovery-time feature protocol to the same balanced logistic regression materially improved positive ranking. VIIRS-match recall rose from 0.2989690722 to 0.8041237113, high-ERC-quartile recall rose from 0.3425414365 to 0.4530386740, and fuel-model-188.0 recall rose from 0.0370370370 to 0.2222222222. However, train AUPRC 0.7213156565 versus validation AUPRC 0.3972123087 shows substantial remaining generalization gap, and no-VIIRS-match recall fell from 0.3927492447 to 0.2658610272.
- next_question: After freezing exp-001 for the single official test evaluation, does its held-out 2020 test AUPRC confirm that the large validation gain generalizes without leakage or selection on test data?
- proposal_observation: The metadata-only balanced logistic baseline reached validation AUPRC 0.1841706764 versus train AUPRC 0.3275533213. At its best-F1 threshold it missed 269 of 428 validation positives; misses were concentrated in groups whose defining signals are absent from metadata, including 119 of 181 positives in the high-ERC quartile, 68 of 97 VIIRS-matched positives, and 26 of 27 positives for fuel model 188.0. Its largest standardized coefficients are also dominated by county indicators (absolute magnitudes up to 3.599), suggesting that incident metadata alone is leaning heavily on geography rather than direct fire-environment conditions.
- proposal_hypothesis: Holding the balanced logistic model and its hyperparameters fixed while replacing metadata-only inputs with the official full input protocol will raise 2019 validation AUPRC by at least 0.03, from 0.1841706764 to at least 0.2141706764, because discovery-time weather, VIIRS, fuel, vegetation, terrain, access, and population signals provide direct information for ranking failures that metadata misses.
- proposal_expected_result: Validation AUPRC of at least 0.2142, with fewer than 269 false negatives at the newly selected best-F1 threshold and improved recall in the high-ERC, VIIRS-match, and fuel-model-188.0 breakdowns. A score below 0.2142 would falsify the claimed material ranking gain from adding the full feature protocol under this fixed linear model.
- proposal_reason: This changes one meaningful variable only: feature_protocol from metadata to all. The model, C=1.0, balanced class weighting, and weather_days=5 remain fixed, isolating whether the measured error concentrations and county-dominated coefficients reflect missing time-available environmental information. The full protocol is allowed, respects discovery-time prediction constraints, and does not use the sealed 2020 test year.

## Limitations

- Validation selection can overfit the validation data.
- Repeated seeds measure seed variation, not generalization to new datasets.
- Recorded controller reasoning and test results are report-only historical evidence, never future discovery context.
- Model paths are recorded references; availability and deployability are not attested.
- Prior test exposure recorded for this session: False.

## Evidence references

- `wf-20260913-150158-81be/exp-000` revision `2026-09-13T15:14:40+00:00`
- `wf-20260913-150158-81be/exp-001` revision `2026-09-13T15:16:16+00:00`

## Recorded model references

- `exp-000`: `C:\AI\Projects\focus\artifacts\wf-20260913-150158-81be\exp-000\model`
- `exp-001`: `C:\AI\Projects\focus\artifacts\wf-20260913-150158-81be\exp-001\model`

## Previously recorded official-test evaluation

No recognized official-test result is recorded in this session. No evaluation was requested.

## ARIA interpretation

Request `aria-assistant-9606ca0331764bf5b20abac1b87e3a89`, evidence snapshot `snapshot-c1f13372a3da50f26ea47250`.
The interpretation below refers to its frozen request snapshot, which may predate the tables above.

exp-000 used logistic_regression with feature_protocol metadata, weather_days 5, and hyperparameters {C: 1.0, class_weight: balanced}. [ev-c293e0823c42768c0e60, ev-a96ef8503255ae0aecbc, ev-87749d4e2beead177272, ev-15612dcad7380d3ed943]
On exp-000 result.validation_auprc for result.split val (2019), the supplied value is exactly 0.18417067640399878. [ev-b352506927fa4f483365, ev-922b6273e0f6fe0496ba, ev-c159a5fe38d80eea9a6d]
exp-001 used logistic_regression with feature_protocol all, weather_days 5, and hyperparameters {C: 1.0, class_weight: balanced}. [ev-8f86dc8a69f91e279f0d, ev-3edc0436454f563f8a47, ev-ba3ddf6d15efd6e0551a, ev-0c2010fad869bc0fd547]
On exp-001 result.validation_auprc for result.split val (2019), the supplied value is exactly 0.39721230867438967. [ev-3a3ade7e5a6ecb4bab4e, ev-66dc5058af323df4cf63, ev-12d7b11432eb570a85f9]
The selected runs report the same result.val_size value of 7047, result.val_positives value of 428, result.train_size value of 22576, and result.seed value of 553371. [ev-7a796d2df2448e1fac7e, ev-a31388f0147079c402b5, ev-968be46cee8f43fb4cd0, ev-d298f377437dd9f603e7, ev-1377c6fdd826a5cc168a, ev-9030940888e24c2fc7cc, ev-2b919a9b8f18b897d88d, ev-9a1ab6bc372f8cdecf6d]
For exp-001, result.train_auprc is exactly 0.7213156564817588 while result.validation_auprc is exactly 0.39721230867438967; this is a descriptive train-validation gap, not evidence of a causal mechanism. [ev-f8c8bfe3d521d28f19c6, ev-3a3ade7e5a6ecb4bab4e]

Proposed recommendation: Freeze exp-001 as the recommended configuration among these selected validation runs: model logistic_regression, feature_protocol all, weather_days 5, hyperparameters {C: 1.0, class_weight: balanced}. Advance it to the separately governed official test evaluation without claiming expected test superiority.

Assumptions: The interpretation treats the supplied evidence as an accurate snapshot of the selected runs.; The comparison is restricted to the supplied 2019 validation evidence and does not establish that the feature protocol caused the score difference.; The recommendation prioritizes the stated optimization objective, validation AUPRC, over runtime, feature count, threshold-specific performance, or deployment constraints.
Missing evidence: No sealed 2020 official test result is exposed, so official test superiority cannot be claimed.; No repeated-seed distribution, confidence interval, or statistical significance analysis is supplied.; Only two selected configurations are supplied; controlled ablations are missing, so the contribution of individual feature families cannot be isolated.; No evidence is supplied about calibration, threshold stability on independent data, operational costs, or prospective deployment performance.
ARIA draft limitations: This conclusion ranks only the two selected runs on the supplied 2019 validation objective.; The runs differ in feature protocol, so the observed association must not be interpreted as a causal effect of any individual feature family.; The exp-001 train-validation gap warrants caution, and uncertainty across repeated seeds is unknown.; The sealed official test set remains unexamined; no claim of official test superiority is supported.

### Cited evidence appendix

Values below come from the interpretation’s frozen snapshot, not a newly fetched experiment.

| Evidence ID | Session | Experiment | Field path | Recorded value |
| --- | --- | --- | --- | --- |
| ev-c293e0823c42768c0e60 | wf-20260913-150158-81be | exp-000 | experiment.model | "logistic_regression" |
| ev-a96ef8503255ae0aecbc | wf-20260913-150158-81be | exp-000 | experiment.feature_protocol | "metadata" |
| ev-87749d4e2beead177272 | wf-20260913-150158-81be | exp-000 | experiment.weather_days | 5 |
| ev-15612dcad7380d3ed943 | wf-20260913-150158-81be | exp-000 | experiment.hyperparameters | {"C": 1.0, "class_weight": "balanced"} |
| ev-c159a5fe38d80eea9a6d | wf-20260913-150158-81be | exp-000 | result.score_kind | "VALIDATION_AUPRC" |
| ev-922b6273e0f6fe0496ba | wf-20260913-150158-81be | exp-000 | result.split | "val (2019)" |
| ev-b352506927fa4f483365 | wf-20260913-150158-81be | exp-000 | result.validation_auprc | 0.18417067640399878 |
| ev-968be46cee8f43fb4cd0 | wf-20260913-150158-81be | exp-000 | result.val_positives | 428 |
| ev-7a796d2df2448e1fac7e | wf-20260913-150158-81be | exp-000 | result.val_size | 7047 |
| ev-1377c6fdd826a5cc168a | wf-20260913-150158-81be | exp-000 | result.train_size | 22576 |
| ev-2b919a9b8f18b897d88d | wf-20260913-150158-81be | exp-000 | result.seed | 553371 |
| ev-8f86dc8a69f91e279f0d | wf-20260913-150158-81be | exp-001 | experiment.model | "logistic_regression" |
| ev-3edc0436454f563f8a47 | wf-20260913-150158-81be | exp-001 | experiment.feature_protocol | "all" |
| ev-ba3ddf6d15efd6e0551a | wf-20260913-150158-81be | exp-001 | experiment.weather_days | 5 |
| ev-0c2010fad869bc0fd547 | wf-20260913-150158-81be | exp-001 | experiment.hyperparameters | {"C": 1.0, "class_weight": "balanced"} |
| ev-12d7b11432eb570a85f9 | wf-20260913-150158-81be | exp-001 | result.score_kind | "VALIDATION_AUPRC" |
| ev-66dc5058af323df4cf63 | wf-20260913-150158-81be | exp-001 | result.split | "val (2019)" |
| ev-3a3ade7e5a6ecb4bab4e | wf-20260913-150158-81be | exp-001 | result.validation_auprc | 0.39721230867438967 |
| ev-f8c8bfe3d521d28f19c6 | wf-20260913-150158-81be | exp-001 | result.train_auprc | 0.7213156564817588 |
| ev-d298f377437dd9f603e7 | wf-20260913-150158-81be | exp-001 | result.val_positives | 428 |
| ev-a31388f0147079c402b5 | wf-20260913-150158-81be | exp-001 | result.val_size | 7047 |
| ev-9030940888e24c2fc7cc | wf-20260913-150158-81be | exp-001 | result.train_size | 22576 |
| ev-9a1ab6bc372f8cdecf6d | wf-20260913-150158-81be | exp-001 | result.seed | 553371 |
