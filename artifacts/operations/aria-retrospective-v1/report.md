# Wildfire autonomous researcher retrospective


## Executive finding

Across **21 actual experiments in four sessions**, the project tested **13 unique configurations** using one research seed (`553371`) for iterative validation selection. The largest repeated validation transitions were metadata-only logistic regression **0.1841706764** → full-feature logistic regression **0.3972123087** → default XGBoost **0.4829886184**. The longer session then found a single-seed validation best of **0.4993702499** at `scale_pos_weight=1.5`.

The two saved final-evaluation summaries report five-local-seed 2020 test means of **0.5413360026 ± 0.0024028513** and **0.5436604938 ± 0.0017356793**, versus the published reference **0.533**. These are **descriptive above-reference results, not certified benchmark wins** because the paper's seed list is unpublished, the later session followed prior test disclosure, and historical fitted models/test predictions were not retained.

### Refreshed scope before this report run

- 49 runs: 21 experiments, 20 ARIA uploads, 3 final decisions, 2 final evaluations, 1 control, 1 smoke, 1 verification.
- Run states: 49 finished; 0 failed, crashed, or running.
- Research artifacts inspected: 5 state, 17 proposal, 3 decision, and 2 final-evaluation collections. Prediction artifacts were not opened; raw test data was not accessed.
- [Focused live workspace](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher?nw=yhc341igcw4) — experiments/final evaluations only, grouped by session; controller noise excluded.
- [Weave traces](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/weave).

## Independent experiment analysis

1. **Full discovery-time features were the largest replicated validation gain.** metadata-only logistic 0.1841706764 to full-feature logistic 0.3972123087, delta +0.2130416323, repeated exactly in three sessions with the same seed/config. *Interpretation:* Descriptive within the fixed 2019 validation protocol; repeated values are not independent seeds.

2. **The bundled model-family transition improved validation ranking.** full-feature logistic 0.3972123087 to default XGBoost 0.4829886184, delta +0.0857763097, repeated in three sessions. *Interpretation:* The transition changes algorithm family and its associated hyperparameters, so it is not attribution to a single XGBoost mechanism.

3. **Depth 3 modestly improved over depth 4.** 0.4829886184 to 0.4867164182, delta +0.0037277999; train-validation gap decreased from 0.2439362472 to 0.1728497379. *Interpretation:* Clean incumbent-relative max_depth comparison under one research seed; the gain is small.

4. **Several incumbent-relative regularization/ablation trials did not improve AUPRC.** depth 2: 0.4754578025; min_child_weight 3: 0.4849006216; colsample 0.6: 0.4829902920; all_without_access: 0.4768519159; learning_rate 0.02: 0.4753333695, each versus depth-3 incumbent 0.4867164182. *Interpretation:* Compared to the incumbent configuration to avoid causal interpretation of confounded adjacent resets.

5. **Lower class weighting was the successful late search direction.** scale_pos_weight auto 0.4867164182, 6.0 0.4877548637, 3.0 0.4923155668, 1.5 0.4993702499, 0.75 0.4980376701. *Interpretation:* The measured single-seed optimum among tested values was 1.5; 0.75 reversed the trend.

6. **Fresh bounded session reproduced the first three-step path.** wf-20260913-123756-7824: 0.1841706764 -> 0.3972123087 -> 0.4829886184; final KEEP exp-002. *Interpretation:* Exact same seed/config reproduces execution, not independent statistical generalization.

7. **Final test summaries are above the 0.533 reference but are not certified benchmark wins.** live1 0.5413360026 ± 0.0024028513; session2 0.5436604938 ± 0.0017356793 over five local seeds. *Interpretation:* Published seed list is unavailable; validation and test are different year populations; session2 began after session1 test disclosure.

### Sessions

| Session | Experiments | Status | Best validation AUPRC | Selected experiment | Final decision |
|---|---:|---|---:|---|---|
| `wf-20260913-live1` | 4 | complete | 0.4867164182 | exp-003 | KEEP exp-003 → select exp-003 |
| `wf-20260913-104003-2c71` | 13 | complete | 0.4993702499 | exp-011 | REJECT exp-012 → select exp-011 |
| `wf-20260913-fresh-audit` | 1 | CANCELLED (local runner record; cloud state artifact stale) | 0.1841706764 | exp-000 | — |
| `wf-20260913-123756-7824` | 3 | complete | 0.4829886184 | exp-002 | KEEP exp-002 → select exp-002 |
## All actual experiments

Each delta is against the **best prior validation incumbent in that session**, not blindly against the adjacent run. Changed-field lists expose confounded resets; no causal claim is made for multi-field transitions.

| Session | Experiment | Model / protocol | Key changed fields vs incumbent | Val AUPRC | Δ vs incumbent | Decision |
|---|---|---|---|---:|---:|---|
| `wf-20260913-live1` | [exp-000](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/kb9c79fw) | logistic_regression / metadata | baseline | 0.1841706764 | — | KEEP |
| `wf-20260913-live1` | [exp-001](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/960bw9j1) | logistic_regression / all | feature_protocol | 0.3972123087 | 0.2130416323 | KEEP |
| `wf-20260913-live1` | [exp-002](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/fq4le8sk) | xgboost / all | hyperparameters.C, hyperparameters.class_weight, hyperparameters.colsample_bytree, hyperparameters.gamma, hyperparameters.learning_rate, hyperparameters.max_depth, hyperparameters.min_child_weight, hyperparameters.n_estimators, hyperparameters.reg_alpha, hyperparameters.reg_lambda, hyperparameters.scale_pos_weight, hyperparameters.subsample, model | 0.4829886184 | 0.0857763097 | KEEP |
| `wf-20260913-live1` | [exp-003](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/p64qsxsl) | xgboost / all | hyperparameters.max_depth | 0.4867164182 | 0.0037277999 | KEEP |
| `wf-20260913-104003-2c71` | [exp-000](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/zffjmu71) | logistic_regression / metadata | baseline | 0.1841706764 | — | KEEP |
| `wf-20260913-104003-2c71` | [exp-001](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/yxpoam8f) | logistic_regression / all | feature_protocol | 0.3972123087 | 0.2130416323 | KEEP |
| `wf-20260913-104003-2c71` | [exp-002](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/sw6eu8l8) | xgboost / all | hyperparameters.C, hyperparameters.class_weight, hyperparameters.colsample_bytree, hyperparameters.gamma, hyperparameters.learning_rate, hyperparameters.max_depth, hyperparameters.min_child_weight, hyperparameters.n_estimators, hyperparameters.reg_alpha, hyperparameters.reg_lambda, hyperparameters.scale_pos_weight, hyperparameters.subsample, model | 0.4829886184 | 0.0857763097 | KEEP |
| `wf-20260913-104003-2c71` | [exp-003](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/iu3n6tme) | xgboost / all | hyperparameters.max_depth | 0.4867164182 | 0.0037277999 | KEEP |
| `wf-20260913-104003-2c71` | [exp-004](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/3xanyjye) | xgboost / all | hyperparameters.max_depth | 0.4754578025 | -0.0112586157 | REJECT |
| `wf-20260913-104003-2c71` | [exp-005](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/3c1o1b9n) | xgboost / all | hyperparameters.min_child_weight | 0.4849006216 | -0.0018157967 | REJECT |
| `wf-20260913-104003-2c71` | [exp-006](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/lc1oe0pu) | xgboost / all | hyperparameters.colsample_bytree | 0.4829902920 | -0.0037261262 | REJECT |
| `wf-20260913-104003-2c71` | [exp-007](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/1wanlyuj) | xgboost / all_without_access | feature_protocol | 0.4768519159 | -0.0098645023 | REJECT |
| `wf-20260913-104003-2c71` | [exp-008](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/hdekadle) | xgboost / all | hyperparameters.learning_rate | 0.4753333695 | -0.0113830487 | REJECT |
| `wf-20260913-104003-2c71` | [exp-009](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/o0rkbizb) | xgboost / all | hyperparameters.scale_pos_weight | 0.4877548637 | 0.0010384454 | KEEP |
| `wf-20260913-104003-2c71` | [exp-010](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/z8czs2f9) | xgboost / all | hyperparameters.scale_pos_weight | 0.4923155668 | 0.0045607032 | KEEP |
| `wf-20260913-104003-2c71` | [exp-011](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/6f10ttcl) | xgboost / all | hyperparameters.scale_pos_weight | 0.4993702499 | 0.0070546831 | KEEP |
| `wf-20260913-104003-2c71` | [exp-012](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/qstuzf1c) | xgboost / all | hyperparameters.scale_pos_weight | 0.4980376701 | -0.0013325798 | REJECT |
| `wf-20260913-fresh-audit` | [exp-000](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/tnzdsn2b) | logistic_regression / metadata | baseline | 0.1841706764 | — | CANCELLED after baseline |
| `wf-20260913-123756-7824` | [exp-000](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/8l6w97q5) | logistic_regression / metadata | baseline | 0.1841706764 | — | KEEP |
| `wf-20260913-123756-7824` | [exp-001](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/nhl61zqf) | logistic_regression / all | feature_protocol | 0.3972123087 | 0.2130416323 | KEEP |
| `wf-20260913-123756-7824` | [exp-002](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/v6rfe54x) | xgboost / all | hyperparameters.C, hyperparameters.class_weight, hyperparameters.colsample_bytree, hyperparameters.gamma, hyperparameters.learning_rate, hyperparameters.max_depth, hyperparameters.min_child_weight, hyperparameters.n_estimators, hyperparameters.reg_alpha, hyperparameters.reg_lambda, hyperparameters.scale_pos_weight, hyperparameters.subsample, model | 0.4829886184 | 0.0857763097 | KEEP |

## ARIA decision-consistency audit

- Proposal artifacts: **17**; non-baseline experiments: **17**.
- Proposals with exactly one executed config match: **17/17**.
- Proposal `previous_decision` values matching final state history: **17/17**.
- Experiments carrying a recorded decision: **20/21**. The remaining baseline belongs to `fresh-audit`, which local SQLite records as **CANCELLED** after its custom name failed to match the automation; cloud research-state `v0` is stale at `awaiting_aria_proposal`. This is a source discrepancy, not a currently stalled session.
- Recorded decisions consistent with KEEP iff the experiment became the numeric validation incumbent, otherwise REJECT: **20/20**.
- Final decisions selecting the numeric session best: **3/3**.

The fresh bounded session `wf-20260913-123756-7824` is internally consistent: **0.1841706764 → 0.3972123087 → 0.4829886184**, followed by final **KEEP exp-002**. This exact replay uses the same seed/config and demonstrates deterministic execution reproducibility, not independent statistical replication.


## Weave latency, error, and observability audit

- **126 calls**, all **126 roots** and **0 children**.
- **0 error/descendant-error/exception calls**; all 126 summaries report success.
- Persisted `ended_at` is present for **126/126** calls. The earlier 0/126 statement came from a projected response that omitted the field; it was not missing persisted telemetry. Latency statistics remain based on `summary.weave.latency_ms` for consistency with the original analysis.
- Usage/token/cost fields are present for **0/126** calls. This means token accounting and internal model-call latency are **missing**, not zero.
- **77/126** calls have `wb_run_id`; all 77 join to runs in the fixed 49-run source snapshot. Joined historical attribution is: `wf-20260913-live1` 13, `wf-20260913-104003-2c71` 41, `wf-20260913-fresh-audit` 3, `wf-20260913-123756-7824` 18, plus one smoke and one audit call. The remaining 49 calls lack `wb_run_id` and are not assigned to a session by this join.
- The 21 `execute_training` calls dominate observed latency: median **67.193 s**, p95 **116.717 s**, maximum **136.231 s**. Publishing state is the next visible cost: median **1.940 s**, p95 **2.418 s**.

| Operation | Calls | Median latency | p95 latency | Max latency | Errors |
|---|---:|---:|---:|---:|---:|
| `audit_trace_link` | 1 | 0.001 s | 0.001 s | 0.001 s | 0 |
| `evaluate_result` | 21 | 0.000 s | 0.000 s | 0.000 s | 0 |
| `execute_training` | 21 | 67.193 s | 116.717 s | 136.231 s | 0 |
| `publish_research_state` | 25 | 1.940 s | 2.418 s | 2.774 s | 0 |
| `receive_aria_output` | 20 | 0.000 s | 0.001 s | 0.001 s | 0 |
| `record_aria_decision` | 20 | 0.002 s | 0.020 s | 0.030 s | 0 |
| `smoke_op` | 1 | 0.000 s | 0.000 s | 0.000 s | 0 |
| `validate_experiment` | 17 | 0.000 s | 0.362 s | 1.807 s | 0 |
## Critical interpretation caveats

- The 0.4993702499 value is 2019 validation AUPRC for one research seed; 0.5436604938 is mean 2020 test AUPRC over five final seeds. They are different populations and estimators and must not be compared as a gain.
- The paper reports a five-seed mean of 0.533 but does not publish its seed list; seed-matched uncertainty or significance cannot be assessed.
- Session wf-20260913-104003-2c71 began after the wf-20260913-live1 test result was disclosed. Its later test result is descriptive and not an independent blind confirmation.
- Historical test prediction files and fitted model files were not preserved. The retrospective did not access test data and cannot independently recompute test metrics or conduct test error analysis.
- Repeated validation scores across sessions use the same research seed and configuration; they demonstrate deterministic reproducibility, not independent replication.
- All 126 Weave calls are roots and no token/usage/cost fields are present. Internal ARIA reasoning and model-call latency are missing from the trace, not zero.
- Correction: the original projection omitted `ended_at` and `wb_run_id`. A persisted-field re-query found `ended_at` on 126/126 calls and `wb_run_id` on 77/126; all 77 linked spans join to runs in the fixed source snapshot.

## Reproducibility and preservation gaps

The run summaries and research artifacts are sufficient to reconstruct config/metric/decision history. They are insufficient to independently reproduce historical test evaluations because the fitted models and historical test prediction files were not preserved. This retrospective did not train, submit jobs, modify existing automations, mutate experiment metrics, or access raw test examples.


## Method

The analysis refreshed all project run summaries/configs, restricted “actual experiments” to `job_type=experiment`, reconstructed sessions from run groups and research-state artifacts, and compared each experiment with the best prior validation score in its own session. Proposal experiments were normalized and matched against executed configs; proposal prior-decisions were checked against final state history; final decisions were checked against numeric session winners. Weave calls were fetched with projected metadata/summary fields only; inputs, outputs, internal reasoning, prediction tables, and raw test data were not fetched.


## Published outputs

- Research report: https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/reports/Wildfire-Autonomous-Researcher-Retrospective-—-2026-09-13--VmlldzoxNzkyNDE5Ng==
- Focused saved workspace: https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher?nw=yhc341igcw4
- Weave traces: https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/weave


> **Verification correction — 2026-09-13:** The source inventory remains fixed at 49 runs. Persisted Weave telemetry has `ended_at` on 126/126 calls and `wb_run_id` on 77/126; linked spans can be joined to run groups for historical session attribution. Local SQLite records `wf-20260913-fresh-audit` as CANCELLED after its baseline because its custom name did not match the automation, while cloud research-state `v0` remains stale at `awaiting_aria_proposal`.
