# Demo script (about 3 minutes)

## Before the demo

```bash
.\.venv\Scripts\python.exe -m uvicorn wildfire_researcher.api:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev
```

Open http://localhost:3000 and pick session `wf-20260913-live1` (verified, complete, final-evaluated). Keep a W&B tab on the project's Weave traces and Automations → History.

## Screen 1 — the question (10 seconds)

Top cards: **Published benchmark 53.3%** (official test split) · **Our official test result 54.1%** (frozen exp-003, 5 seeds, protocol-matched) · **Delta +0.8 pts** · **PUBLISHED BENCHMARK BEATEN**. Say: the agent started from an 18.4% metadata-only baseline; every step after that was chosen by ARIA.

## Screen 2 — watch the researcher think

Click **REPLAY VERIFIED RUN**. The trajectory animates through the stored experiments (no retraining, pill reads REPLAYING VERIFIED RUN): 18.4% → 39.7% (features metadata → all) → 48.3% (XGBoost) → 48.7% (max_depth 3). The ARIA RESEARCHER panel shows, in ARIA's own words, the observation ("missed 269 of 428 validation positives… Q4-high ERC group…"), hypothesis, experiment, result, KEEP/REJECT with reason, learning and next question.

Click an experiment row to open details: configuration, validation metrics, false negatives by VIIRS detection / ERC quartile / month / state / fuel model, feature importance, the W&B run and Weave links, and the proposal artifact reference.

## Screen 3 — the evidence

- W&B run of exp-002 or exp-003: config carries ARIA's hypothesis, reason and change; metrics include validation AUPRC, delta, PR curve table.
- Weave traces filtered to that run: `receive_aria_output` (artifact digest and ARIA's verbatim proposal) → `validate_experiment` → `execute_training` → `evaluate_result` → `record_aria_decision` → `publish_research_state`.
- Automations → History: each dispatch to ARIA with its conversation.
- Artifacts: `wf-20260913-live1-state` (v0..v5), `-proposal-r1..r3`, `-decision-final`, `-final-evaluation`.

## Screen 4 — live (optional, ~4 minutes per cycle)

Set budget, keep ARIA mode `connected`, click **START AUTONOMOUS RESEARCH**. The baseline trains in seconds; the pill reads LIVE RUN; the ARIA panel switches to WAITING FOR ARIA; ~60–90 s later ARIA's proposal appears and training starts. Nothing was pre-scripted: the generic automation invokes a fresh ARIA conversation on every finished run.

## Closing

"N autonomous experiments, zero human model or feature selection during the loop. The only human choices were the fixed baseline and the budget. The benchmark claim is gated by the backend under the official protocol, with the caveats listed in BENCHMARK_PROTOCOL.md."

Footer on every screen: *Research prototype using historical public data. Not for operational wildfire response.*
# Audit update for presenters

Use [AUDIT_FIXES.md](AUDIT_FIXES.md) for current claim language. The recorded
0.5413 and 0.5437 means remain above the 0.533 reference, but the current UI does
not certify superiority. Exact paper seeds are unknown and session 2 followed
session 1's test disclosure. Original event messages are historical evidence.

For backend-independent playback, use **IMPORT REPLAY JSON** and select
`artifacts/<session>/replay.json`. Load the frontend first; imported replay,
metrics and experiment details then need no API/database. W&B links need internet.
