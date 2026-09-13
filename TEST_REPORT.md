# Test report — 2026-09-13

## ARIA operations follow-up

Final suite: **80 passed**, three upstream warnings, **188.01 seconds**.
Frontend: **3 tests passed**, TypeScript, ESLint, and production build passed.
The completed real-ARIA Launch session scored **0.1841706764 → 0.4829886184 →
0.4999662448 validation AUPRC** and ended with ARIA's KEEP recommendation.
Cloud verification matched all three measured runs, final artifacts, and 17 linked
experiment/exchange Weave spans with no problems. All three ARIA-submitted Launch
controllers carry native W&B ARIA conversation provenance. Operational alerts were
submitted for the real bootstrap failure, budget exhaustion and final decision.
The historical winning model was reconstructed with exactly matching validation
probabilities and its Registry digest was verified. No new official test evaluation ran.
See [OPERATIONS.md](OPERATIONS.md) for evidence, links, and local-compute limitations.

The older sections below describe earlier verification milestones.

## Audit follow-up validation

Final Python suite: **70 passed**, three upstream deprecation warnings, 140.85 s.
Command: `.\.venv\Scripts\python.exe -m pytest -q`.
Frontend: **3 tests passed**, `npx tsc --noEmit`, `npx eslint src`, and
`npm run build` all passed. No new official test evaluation was performed.

See [AUDIT_FIXES.md](AUDIT_FIXES.md) for the changes and remaining limitations.
The audit added 20 Python regression tests and 3 frontend replay tests. Frontend
type checking, ESLint, production build and the replay tests pass. Browser import
and detail viewing were verified with the backend stopped. A live W&B smoke run
`i3p96ssn` verified the new external trace association, without ARIA invocation,
training or benchmark metrics. The original two final results were rechecked
against W&B and retained unchanged. The refreshed session-2 replay includes its
final result. The older sections below describe the pre-audit implementation.

Machine: Windows 11, 8 logical CPUs, 32 GB RAM, no CUDA GPU. Python 3.12.10 in `.venv`; Node 24.18.1; xgboost 3.4.1, scikit-learn 1.9.1, wandb 0.30.0, weave 0.53.9, Next.js 16.3.5.

## Automated tests

Command: `.\.venv\Scripts\python.exe -m pytest -q`

| File | Covers | Result |
|---|---|---|
| `tests/test_experiments.py` (29) | strict proposal parsing: unknown keys, wrong types (bool as int, "5" as int), NaN/Infinity, out-of-range values, unsupported models/protocols, path/command injection strings, stale revision, wrong session, duplicate proposal id, duplicate canonical configuration (weather_days canonicalised), decision must target the last experiment, budget exhausted, final-decision schema, official defaults, manifest lists the 21 official protocols | pass |
| `tests/test_protocol.py` (6) | pinned commit, split years and cohort sizes (22,576 / 7,047), test split never exposed to the research loader, forbidden columns absent from every cache, train-only imputation/scaling, AP-vs-trapezoid metric parity, degenerate labels and NaN scores raise | pass |
| `tests/test_runner.py` (2) | real metadata logistic regression on the official cache, prediction file, DEV_SCORE labelling for subsampled runs | pass |
| `tests/test_loop_offline.py` (5) | full loop with the labelled fallback stub and no W&B: persistence of every experiment, decision, ARIA message; numeric best independent of decisions; state file free of test metrics; replay export; restart recovery re-runs an interrupted claim without duplicating; cancel stops at a safe point; database rejects duplicate configuration claims; state has no secrets and correct budget semantics | pass |
| `tests/test_api.py` (5) | health, 404s, bad mode rejected, start → run → complete via API with fallback stub (DEV_SCORE, benchmark not beaten), details/events/replay endpoints, persistence across a fresh store, resume rejected on complete session, automation prompt under the 4,000-char limit (generic and session-specific) | pass |
| `tests/test_nudge.py` (2) | ARIA silence: worker re-publishes state (new revision) and then accepts the answer; gives up after `ARIA_MAX_NUDGES` without inventing an experiment | pass |
| `tests/test_official_parity.py` (1) | runs the pinned official `train.py` (logistic regression, metadata, seed 553371) and matches our runner's validation AUPRC and AUROC within 2e-3 | pass |

Total: **50 passed** (about 2.5 min; all training is real and lightweight; no network). Network-dependent behaviour is covered by the live runs below, not by mocks.

Frontend: `npx tsc --noEmit` clean; `npx eslint src` clean (two React-compiler rule violations fixed during development); `npm run build` succeeds (static prerender).

## Live verification with real ARIA (no mocks)

### Tracking smoke (`scripts/smoke_tracking.py`)
One W&B run, one Weave op, one `research-state` artifact published and fetched back by qualified name; missing artifact lookup returns `None`. Run `36v9ne1r`.

### Session `wf-20260913-live1` (budget 3, CLI worker, session-specific automation)
Timeline (UTC): baseline finished 10:16:52 → ARIA proposal r1 validated 10:17:59 → exp-001 done 10:18:17 → proposal r2 10:19:40 → exp-002 done 10:21:06 → proposal r3 10:22:27 → exp-003 done 10:24:13 → final decision 10:25:20. Every proposal passed validation on the first attempt; zero rejections; zero manual steps after `resume` was started.

| Exp | Controller | Configuration | Validation AUPRC | Delta | ARIA decision |
|---|---|---|---:|---:|---|
| 0 | baseline | logistic_regression · metadata | 0.1842 | — | KEEP (reference) |
| 1 | ARIA | logistic_regression · all | 0.3972 | +0.2130 | KEEP |
| 2 | ARIA | xgboost · all (official config) | 0.4830 | +0.0858 | KEEP |
| 3 | ARIA | xgboost · all · max_depth 3 | 0.4867 | +0.0037 | KEEP, recommended for freezing |

Official final evaluation (`final-eval`, frozen exp-003, sealed 2020 test year, official metric code):

| Seed | val AUPRC | test AUPRC |
|---|---:|---:|
| 553371 | 0.4867 | 0.5452 |
| 553372 | 0.4736 | 0.5421 |
| 553373 | 0.4781 | 0.5398 |
| 553374 | 0.4832 | 0.5404 |
| 553375 | 0.4864 | 0.5392 |

Mean test AUPRC **0.5413 ± 0.0024** vs published 0.533 → `benchmark_beaten = true`, `protocol_matched = true`. Caveat: the official five-seed list is not public. W&B run `4gvl293f`; artifact `wf-20260913-live1-final-evaluation:v0`.

Remote verification: 4 experiment runs + final-decision run + final-evaluation run in the project; Weave traces for `receive_aria_output`, `validate_experiment`, `execute_training`, `evaluate_result`, `record_aria_decision`, `publish_research_state` associated with their runs; artifacts `-state` v0–v5, `-proposal-r1..r3`, `-decision-final`, `-predictions` per experiment.

### Official-script parity (manual)
`WildfireIA/train.py --model xgboost --input_protocol all --seed 553371` (depth 4): val 0.4848, test 0.5285, `xgboost_fit_note = no_early_stopping_api` (the official script drops early stopping on xgboost 3.x). Our runner for the same configuration and seed: val 0.4830 with early stopping at iteration 459. Same protocol; the difference is the early-stopping behaviour the official code intended. Documented in `BENCHMARK_PROTOCOL.md`.

### Session `wf-20260913-104003-2c71` (budget 12, started from the UI, generic automation)
Started by clicking START AUTONOMOUS RESEARCH in the console (worker thread inside the FastAPI process). ARIA derived the session id from the run name as instructed by the generic prompt and proposed exp-001 within 70 s of the baseline finishing. Outcome: see the addendum at the end of this file.

### Bug found only by live testing
The first UI-started session failed immediately with `UNIQUE constraint failed: experiments.id`: experiment ids (`exp-000`…) were globally unique in SQLite, so any second session collided. Fixed by keying experiments on `(session_id, id)` with an automatic migration (`Store._migrate_experiments_pk`); the empty errored session row was removed. Offline tests had missed it because each test used a fresh database.

### Two more issues found only by the live run
1. **Dropped W&B event.** After exp-008 of session 2 finished (11:02 UTC), the automation never fired (history shows 8 dispatches for 9 finished runs) and the worker waited 10 minutes. Fix: `ResearchLoop._wait_with_nudges` re-publishes the state through a control run (`<session>-control-r<N>`, a fresh run-finished event) after `ARIA_NUDGE_SECONDS` (420 s), up to `ARIA_MAX_NUDGES` (2) times, then times out. The worker still never chooses an experiment itself. Covered by `tests/test_nudge.py` (2 tests).
2. **Resume after cancel was a no-op.** `ResearchLoop.run` treated `cancelled` like `complete`. Fixed; `test_cancel_stops_at_safe_point` now also resumes the cancelled session and expects it to complete. Session 2 was cancelled, the API restarted with the fix, and the session resumed from the UI/API without losing any of its 9 experiments.

## Browser end-to-end check (in-app Chromium, 1440×1000)
- Console loads, polls every 3 s, survives refresh (session remembered in localStorage, history from SQLite).
- START AUTONOMOUS RESEARCH creates a session, the dropdown switches to it, pill shows LIVE RUN, ARIA panel shows WAITING FOR ARIA then the proposal.
- REPLAY VERIFIED RUN animates the stored experiments (pill: REPLAYING VERIFIED RUN, "no retraining").
- Cards show PUBLISHED BENCHMARK 53.3% (official test), OUR OFFICIAL TEST RESULT 54.1% only after final evaluation, delta only after final evaluation, PUBLISHED BENCHMARK BEATEN status from the backend flag.
- Details drawer: opened via the per-row `details` button / chart point (keyboard reachable, Escape closes); verified in the browser after the accessibility fix.
- Footer disclaimer present on every screen.

## Skipped / not done, and why
- CoreWeave / W&B Launch execution: no cluster credentials or budget were available; training ran on the local CPU (~2 s LR metadata, ~20 s LR full, ~90–140 s XGBoost full). The executor is an adapter so a hosted executor can be added.
- Temporal/spatial representations: out of scope for the tabular P0; the 2.4 GB patch tables were not downloaded.
- Frontend unit tests: not written; coverage is the API tests plus the browser walkthrough above.
- ARIA internal-step tracing: not available through the artifact path; only received outputs are traced (stated in `AUTOMATION.md`).

## Addendum: session `wf-20260913-104003-2c71` outcome (budget 12, real ARIA, started from the UI)

| Exp | Change (vs incumbent) | Validation AUPRC | Delta vs best | ARIA decision |
|---|---|---:|---:|---|
| 0 | baseline: logistic regression, metadata | 0.1842 | — | KEEP (reference) |
| 1 | features metadata → all | 0.3972 | +0.2130 | KEEP |
| 2 | model → xgboost | 0.4830 | +0.0858 | KEEP |
| 3 | max_depth 4 → 3 | 0.4867 | +0.0037 | KEEP |
| 4 | max_depth 3 → 2 | 0.4755 | −0.0113 | REJECT |
| 5 | min_child_weight 1 → 3 | 0.4849 | −0.0018 | REJECT |
| 6 | colsample_bytree 0.8 → 0.6 | 0.4830 | −0.0037 | REJECT |
| 7 | features all → all_without_access | 0.4769 | −0.0099 | REJECT |
| 8 | learning_rate 0.03 → 0.02 | 0.4753 | −0.0114 | REJECT |
| 9 | scale_pos_weight auto (12.25) → 6 | 0.4878 | +0.0010 | KEEP |
| 10 | scale_pos_weight 6 → 3 | 0.4923 | +0.0046 | KEEP |
| 11 | scale_pos_weight 3 → 1.5 | 0.4994 | +0.0071 | KEEP, recommended to freeze |
| 12 | scale_pos_weight 1.5 → 0.75 | 0.4980 | −0.0013 | REJECT (final decision) |

Every proposal was a single-variable change against the incumbent and passed validation first time (13 W&B runs, 15 artifacts, 39 run-attached Weave calls, `scripts/verify_remote.py` reports no problems). One W&B run-finished event was dropped after exp-008; the nudge recovery re-triggered ARIA through a control run (`-control-r10`) and ARIA answered 80 s later. The session was cancelled/resumed once to deploy that fix; no experiment was lost or duplicated.

Official final evaluation of frozen exp-011 (xgboost, all, depth 3, scale_pos_weight 1.5):

| Seed | val AUPRC | test AUPRC |
|---|---:|---:|
| 553371 | 0.4994 | 0.5446 |
| 553372 | 0.4954 | 0.5434 |
| 553373 | 0.4984 | 0.5449 |
| 553374 | 0.4933 | 0.5447 |
| 553375 | 0.4964 | 0.5407 |

Mean test AUPRC **0.5437 ± 0.0017** vs published 0.533 (+1.07 pts) → `benchmark_beaten = true`, `protocol_matched = true`; W&B run `uqf6weq6`, artifact `wf-20260913-104003-2c71-final-evaluation:v0`. Same caveats as session 1 (unpublished official seed list; margin of about one point).

## Agent evaluation (Weave Evaluations)

`wildfire_researcher/agent_evals.py` + `scripts/run_agent_evals.py` evaluate ARIA itself, not the classifier.
Each row is one real exchange: the `<session>-state:r<N>` artifact ARIA read and the proposal or final
decision it published. The Weave "model" replays recorded outputs, so scores judge what ARIA actually did.

Published to the project's Evals tab as `aria-agent-eval-v1` (earlier grounding rule) and `aria-agent-eval-v2`
(final scorers), dataset `aria-research-exchanges` (39 exchanges from 8 sessions: 33 proposals, 6 final decisions).

| Scorer | v2 result | Meaning |
|---|---:|---|
| contract.valid | 39/39 | passes the live validator (schema, bounds, revision, session, duplicates) |
| one_change | 32/33 | exactly one variable versus the incumbent best; the miss is the Launch session's first proposal (model + features at once) |
| grounded_fraction | 0.997 | numbers ARIA cites as facts exist in the state it saw, or are a difference of two such numbers; configuration numbers excluded from the pool |
| decision.consistent | 39/39 | KEEP iff measured delta vs best >= 0 |
| decision.within_noise | 5 | decisions whose |delta| < 0.003 (about the seed std): correct by rule, but not distinguishable from noise |
| prediction.direction_hit | 24/33 | the experiment improved on the best when ARIA predicted it would |
| prediction.target_hit | 23/33 | measured score reached the numeric target ARIA stated |
| novelty | 33/33 | no repeated configuration |

Unit tests: `tests/test_agent_evals.py` (5). Found while building it: the worker recorded the pre-nudge
revision on ARIA message rows (fixed in `loop.py`; the evaluation trusts the revision ARIA echoes).
`aria-agent-eval-v4-judged` (v3 had 14 empty judge replies before the retry/budget fix) adds the W&B Inference judge (`openai/gpt-oss-120b` via `api.inference.wandb.ai`) on the 33 proposals: it asks whether the hypothesis is falsifiable and follows from the observation. Its result is in the Evals tab next to the deterministic scorers; treat it as a second opinion, not ground truth. v4: 33/33 falsifiable, 33/33 follow from the observation, 0 judge errors. Full suite after these additions: 384 passed.
