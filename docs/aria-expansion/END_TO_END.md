# Connected end-to-end acceptance — 13 September 2026

The app was exercised against its local frontend (port 3000), live API (port 8000), real W&B/ARIA transport, and canonical WildfireIA training data. No synthetic training result was substituted.

## Reviewed study

Session: `wf-20260913-190606-4a5b`. Source request: `aria-assistant-7382cee815a0425fba4236a07284ad70`. Reviewed draft: `draft-39650b97c60a47ffb8fa0a8160fc8f71`.

The reviewed configuration started from the UI. The study ran one fixed metadata logistic-regression baseline and one ARIA-proposed all-feature XGBoost candidate, then received its final ARIA decision and completed. The candidate matched the reviewed configuration exactly. Training used 22,576 records from 2016–2018; validation used 7,047 records from 2019.

| Recorded result | Baseline exp-000 | Candidate exp-001 |
| --- | ---: | ---: |
| Validation average precision | 0.18417067640399878 | 0.48606306740555777 |
| Runtime seconds | 6.15599999999904 | 231.06299999999828 |
| California false negatives | 18 | 14 |
| California false positives | 10 | 17 |
| California recall | 0.18181818181818182 | 0.36363636363636365 |

California contains 440 validation examples, including 22 positives. The reviewed proposal required false negatives ≤11, recall ≥0.50, false positives ≤20, and overall AP ≥0.47. **The California objective was not met**: the candidate passed the global AP and false-positive limits but failed the false-negative and recall criteria. The original proposal source candidate already had FN14/FP17/recall0.3636, so this result did not improve that source subgroup outcome.

## Paired-seed verification

Existing reviewed plan `verify-47500795743a45b9ad1ecf2b16bfdea6` uses seeds 17 and 42 and a separate maximum of four training jobs. It was started through the API with its frozen plan hash only after the discovery worker finished. All four actual training jobs completed. Both seed pairs improved validation AP. Mean paired delta: 0.29357908546584705; sample standard deviation: 0.000586312818198978. Claim eligibility remains false: this is validation seed variation, not independent generalization evidence.

| Seed | Baseline AP | Candidate AP | Paired delta |
| --- | ---: | ---: | ---: |
| 17 | 0.18417067640399878 | 0.47816434763949095 | 0.29399367123549214 |
| 42 | 0.18417067640399878 | 0.4773351761002007 | 0.29316449969620195 |

## Assistant interpretation and report

A new comparison request `aria-assistant-07a2c05cbd864513b1baed43a0ece9bd` was rejected by the strict numerical grounding validator. The app retained it as a failed response instead of presenting unsupported claims as accepted evidence. The completed findings index was refreshed (43 indexed records). Local frozen report `report-171480b007f041a9b691a8355ff2675a` was created and exported to [e2e-report.md](e2e-report.md) and [e2e-report.json](e2e-report.json). The full verification record is [e2e-verification.json](e2e-verification.json). A fresh ARIA report request, `aria-assistant-bbc90e8eb013486a99e74d7bd9021500`, was dispatched after verification; its narrative was rejected by the strict response validator and is not included in these complete local exports. The local evidence report remains available; neither rejected response is presented as a verified interpretation.

## Validation and limits

Frontend tests: 51 passed. Lint and isolated production build passed, including TypeScript and all routes. A transient-connection-error display issue was fixed: recovered polling clears the load error while preserving independent action errors.

During demo capture the frontend process on port 3000 stopped; it was restarted as a hidden Next dev process (PID 17108), with logs in `tmp/demo-frontend.*`. The API remained healthy and the active training worker was not restarted. The cause of the frontend exit is not established.

This run checks actual local training and connected ARIA execution. Repeated seeds describe seed variation; they do not establish generalization, a confidence interval, deployment readiness, or benchmark superiority. No new official-test evaluation or W&B report publication was requested.
