# Audit recommendations implemented — 2026-09-13

Historical scores, decisions, W&B artifacts and events are preserved. These fixes
strengthen future execution; they do not erase prior test disclosure or recreate
unrecorded native ARIA reasoning. No new official evaluation was run for this work.

## Evaluation and integrity

- A transactional SQLite freeze records the recommended experiment, exact config,
  protocol, implementation hashes, predeclared seed list and prior local test
  exposures. Active/incomplete, fallback, subsampled and unrecommended experiments
  are rejected. Custom, duplicate, empty and invalid seed lists are rejected.
- Repeating a completed evaluation returns its existing result. A different
  candidate/seed list is blocked. Interrupted evaluation resumes the same frozen
  identity, reusing saved per-seed predictions instead of repeating finished seeds.
- Future evaluations save labels, scores, event IDs, fit notes and file hashes for
  every seed. The final W&B artifact includes predictions. Mutated files fail closed.
- `verify-data` checks the 13 canonical files against upstream git/LFS hashes at
  the pinned Hugging Face revision. It independently rebuilds official metadata
  and full-input caches, compares arrays/indexes/preprocessing, then attests their
  file hashes. Final evaluation verifies the clean pinned source, canonical hashes
  and cache hashes before loading the test split.
- This verification passed on the actual local data and both existing caches.
- Research loading now opens only train/validation files. The official parity
  test uses a validation mirror as its required test-shaped fixture; it no longer
  evaluates the real 2020 data during routine tests. Cache creation still processes
  all official splits, as the official builder does.
- Backend/UI separate a recorded result above the reference from a certified
  benchmark claim. Historical `benchmark_beaten` fields remain in original records
  but do not activate the current UI's claim. Exact paper seeds and a fresh
  confirmatory holdout remain unavailable, so new evaluations also carry
  `claim_eligible=false` with explicit limitations.

Run before any new official evaluation:

```powershell
.\.venv\Scripts\python.exe -m wildfire_researcher.cli verify-data
```

Local hash manifests protect against accidental changes, not a hostile operator
who can edit the application, database and manifests. The local exposure ledger
cannot establish what a human or another W&B conversation previously read.

## Worker and tracing

- OS file lease serializes local research and final evaluation across processes.
  API also rejects overlapping session workers. Test leases use temporary directories.
- Training runs in a child process with `MAX_RUNTIME_SECONDS` enforced. Cancellation
  terminates the child and preserves a claimed experiment for resume.
- ARIA receipt/validation/decision spans now associate with the preceding experiment
  run and carry session/revision attributes. This records actual artifact exchange,
  not ARIA internal reasoning. Existing unlinked historical spans are not rewritten.
- New proposal references use immutable artifact versions and retain digests.
- Connected tracing setup failures raise instead of silently dropping tracing.
- Remote verification rejects missing/nonfinite metrics, unfinished runs, missing
  required artifacts/spans and final-result mismatches. New sessions require linked
  ARIA span counts; old sessions retain their documented legacy trace limitation.

One live W&B/Weave smoke run verified association after the W&B run had finished:
[verification run](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/runs/i3p96ssn),
[trace](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/r/call/01a09aaa-fdf6-7c4f-8cb9-48144241903b).
It is explicitly labeled a fixture, with no ARIA invocation, model training or metrics.
Its name does not match the research automation filters. No automation was changed.

## Replay and UI

- Both session exports were refreshed; old exports are preserved beside them as
  `replay.pre-audit.json`. Session 2's export now includes its final evaluation.
- Replay takes a fixed snapshot and stops live polling. Import Replay JSON works
  without the API or database, once the frontend is loaded. Experiment details
  come from the imported record. W&B links still require internet.
- Browser verification: imported session 1 while the backend was stopped, then
  opened its experiment detail drawer successfully. Session 2 replay hides final
  test results until the trajectory reaches its end. The backend was restarted.
- Imported JSON is consistency-checked, not cryptographically authenticated;
  the UI calls this a stored replay rather than certifying external file authorship.
- Pending ARIA observations are now included and rendered. Historical events remain
  labeled as history, not present-day certification.

## Validation

- **70 Python tests passed** (140.85 seconds; three upstream deprecation warnings).
- **3 frontend replay tests passed**. Exact commands are in TEST_REPORT.md.
- New tests cover freeze eligibility/immutability, seed rejection, completed-result
  idempotency, interrupted per-seed resume, saved predictions/replay equality,
  provenance tampering, prior exposure, no test-file reads, train preprocessing
  invariance, worker exclusion, timeout/cancellation and trace context cleanup.
- Three frontend tests cover replay parsing, inconsistent-record rejection and
  preservation of raw historical evidence while suppressing uncertified claims.
- Frontend type checking, ESLint and production build passed.
- Browser replay and live W&B trace-link smoke passed.

The two original test means remain **0.541336** and **0.543660**. Their interpretation
still includes unpublished paper seeds, the documented early-stopping difference,
and session 2 following session 1's test disclosure. New code cannot retroactively
turn those searches into an untouched confirmatory evaluation.
