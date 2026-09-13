# Independent handoff audit — 2026-09-13

This is the preserved pre-fix audit. See [AUDIT_FIXES.md](AUDIT_FIXES.md) for
implemented corrections and [TEST_REPORT.md](TEST_REPORT.md) for current results.

The experiment records are substantive and internally consistent. The implementation
does not yet enforce several scientific safeguards claimed in its documentation.
This audit did not change application code, cloud automations, or recorded results.
It added `scripts/audit_handoff.py` and downloaded evidence under `artifacts/audit/`.

## Verified

- All 50 existing pytest tests passed (56.91 s, two dependency deprecation warnings).
- Frontend `npx tsc --noEmit` passed. A fresh production build/browser walkthrough
  was not part of this focused audit.
- All 17 saved validation AUPRC values across both sessions recompute from their
  stored labels/predictions to within 1e-12. Corresponding W&B runs are finished
  and agree with local scores.
- Session 1 final evaluation: 0.5413360025586591, sample standard deviation
  0.002402851272832847. Session 2: 0.5436604937859502, sample standard deviation
  0.001735679308469574. Both have five seeds. The mean/std arithmetic is correct;
  final JSON files match their W&B v0 artifacts and W&B summary means.
- Evaluated configurations are the recorded ARIA recommendations: exp-003 and
  exp-011 respectively. Each local session event history contains one final
  evaluation start and completion.
- The full-feature cache's IDs, labels, and years match the local canonical table:
  train 22,576/1,704 positives; validation 7,047/428; test 6,168/513.
- The upstream checkout is clean and at the documented pinned commit
  `aba9be9ef046a03e868a61c4139aa5bfcd7b5b56`.
- W&B proposal/final-decision artifact digests match stored references. Project
  Weave contains 104 calls, including 17 ARIA output receipts, 15 proposal validations,
  and 17 decision recordings; those three groups have no reported exceptions.

Limits: final test predictions/models were not saved by the final evaluator.
Therefore this audit verifies final metric arithmetic and cross-storage consistency,
not a fresh prediction-level reproduction of final test AUPRC. No additional final
training was run. Local canonical file bytes were not independently compared with
the Hugging Face revision's file hashes. Original ARIA conversations were not
reopened in the browser during this audit.

## Findings requiring correction

### P1 — Frozen, one-time test evaluation is not enforced

`wildfire_researcher/final_eval.py:32` accepts a session/experiment and immediately
loads the held-out data. It does not require a completed session, completed
experiment, ARIA final recommendation, persisted freeze record, or absence of an
existing final evaluation. `cli.py:152` permits an arbitrary `--experiment`, and
`cli.py:186` permits custom `--seeds`.

A stubbed audit reproduced that an active session, without an ARIA recommendation,
already containing a final evaluation, can reach the test loader for an unfrozen
experiment with one seed. The stub stopped at the loader; it performed no training
and did not modify the live database. Repeated evaluations would overwrite the
session's final evaluation instead of enforcing the documented one-time rule.

Fix: transactional freeze/evaluation records with immutable config, protocol and
predeclared unique seed list; reject uncompleted/unrecommended candidates; return
an existing completed result rather than re-evaluating; resume interrupted seed
work from saved predictions; explicitly classify any exploratory test access.
Add negative tests for all of these conditions.

### P1 — The benchmark-comparability gate fails open

`final_eval.py:21` only checks the firms-only cohort, subsampling setting, and
whether git HEAD is a different known revision. Missing git provenance (`None`)
is accepted. The audit reproduced `(True, [])` for an unknown revision.
`final_eval.py:55` can declare the benchmark beaten with a single custom seed.

The gate does not verify canonical-data hashes, cache provenance, cohort IDs,
split labels, dirty source changes, or the required seed count/uniqueness.
`protocol.ensure_tabular_cache` delegates reuse to official code that only checks
whether `X_train.npy` exists; changing input files or code need not invalidate it.
`protocol.provenance` records a dataset revision constant rather than proving
the current files came from it.

The current checked cache sizes/labels/years are correct; this finding is about
the claim gate's ability to certify future results, not evidence of altered data.
Fix with a fail-closed verified manifest and claim eligibility separate from a
plain numeric comparison. Document the unpublished paper seeds and early-stopping
implementation deviation alongside every comparison.

### P2 — Session 2's exported replay is stale

`artifacts/wf-20260913-104003-2c71/replay.json` has
`session.final_evaluation = null`, although SQLite and the final evaluation artifact
contain the completed 0.54366049 result. All its experiment configurations, results,
scores, and decisions match the database. Session 1's final evaluation is present
in its export.

Fix: export again after final evaluation, and test full session equality as well
as experiment equality. The frontend currently animates the live database view
(`frontend/src/components/Console.tsx:94`) rather than loading the exported replay.
It continues polling, shows the final benchmark outcome from the start, and does
not offer a UI path to import the saved export. This is a stored-history animation,
not yet the advertised database-independent/offline replay experience.

### P2 — ARIA spans are not linked to experiment runs

The 17 receipt, 15 validation, and 17 decision spans exist, but all have no
`wb_run_id`. They execute outside `ExperimentRun`; training/evaluation/state
publication are linked. Consequently the current remote verifier's run-filtered
view only counts three operations per experiment. The report's suggestion that
all research operations are associated with their experiment runs is inaccurate.

Fix: a session/iteration trace hierarchy or explicit attributes/trace IDs attached
to both the asynchronous ARIA exchange and its experiment. Do not fabricate native
ARIA internal reasoning spans. Receipt metadata contains conversation notes but
no thread IDs for these runs; preserve automation conversation IDs where available.

### P2 — Remote verification can pass with missing evidence

`scripts/verify_remote.py:33` compares a potentially NaN metric using
`abs(remote-local) > tolerance`; missing metric → NaN → condition false.
Missing state/final artifacts are displayed but not added to `problems`, and no
minimum trace counts or required operation set are asserted. The successful
verifier result alone is weaker than the documentation implies.

Fix: require finite metrics, finished runs, required artifacts, expected operation
counts, successful calls, exact version/digest/content relationships, and final
evaluation evidence. This audit independently checked the actual final artifacts
and finite scores, so these verifier bugs did not supply the positive conclusions.

## Test isolation: what can and cannot be concluded

Session 1 finished its test evaluation at **10:33:39 UTC**. Session 2 was created
at **10:40:03 UTC**. Thus the broader research process had already exposed the test
set result before the second search began.

The state builder excludes final test metrics, the training fit uses only train
and validation arrays, and the saved inbound proposal text contains no matches
for the inspected reported test scores. Those are positive signs, but not proof
that human guidance, project-wide access, or other ARIA context never used them.
ARIA has access to the same project containing final evaluation runs. The prompt
says to trust only the state, which is an instruction, not an access boundary.

Also, `protocol.load_research_splits` actually calls the official loader, which
reads all three splits, then removes `test`. It does not fit on test data, but
the claims that research code never reads test files and that the split is sealed
are stronger than the implementation. The official parity pytest also executes
official train.py, which writes test metrics while the test assertion checks only
validation. This audit's pytest run executed that existing parity test as written.

I found no direct evidence of test-driven model selection in the inspected
records. I cannot certify that session 2 is a fully untouched confirmatory result.
Do not repair this by pretending the prior test access never happened. Disclose
the chronology, stop adaptive use of this test score, and distinguish exploratory
results from a genuinely precommitted future evaluation.

## Additional implementation gaps

- API permits simultaneous session threads, while `tracking.py:104` uses
  `wandb.init(reinit="finish_previous")` and a global Weave run context. A second
  session can interfere with the first run/trace context. Serialize sessions
  initially or use process-isolated workers. No concurrent live test was performed.
- `MAX_RUNTIME_SECONDS` is configured but never used by the training path;
  cancellation happens between blocking fits. Model ranges are bounded, but there
  is no hard training deadline. Use a bounded subprocess executor.
- `AriaPanel.tsx`'s `latestProposalField` always returns null, so a pending
  experiment's live observation is always a dash. Include observation in pending
  state and render it.
- Tracking initialization errors are silently swallowed in `tracking.op` and
  `ExperimentRun.__enter__`, despite documentation promising visibility.
- The pytest protocol tests inspect metadata assertions for preprocessing; they
  do not directly test that perturbing validation/test data leaves train transforms
  unchanged. There are no final-evaluator guard tests in the 50-test suite.

## Recommended presentation now

“Two ARIA-driven searches produced recorded five-seed test means of 0.5413 and
0.5437, above the published 0.533. We verified the saved validation predictions,
metric aggregation and W&B records. The paper's exact seeds are unavailable, our
XGBoost early-stopping behavior differs from the current official script on this
runtime, and the second search followed disclosure of the first test result.”

The ± values are sample standard deviations across seeds, not standard errors,
confidence intervals, or proof of statistical superiority over the paper.

Official reference consulted: https://github.com/LabRAI/WildfireIA and its local
pinned implementation. The original source documents a fixed input/evaluation
contract; reuse of its code is useful evidence but does not replace runtime
provenance checks or test-access controls.

Machine-readable checks: `artifacts/audit/handoff_audit.json`.
Re-run the additive audit with `.\.venv\Scripts\python.exe scripts/audit_handoff.py`.
