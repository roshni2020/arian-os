# Independent benchmark acceptance report

Status: **in progress â€” final live acceptance not yet complete**. Updated 2026-09-13.

Verification owns `tests/test_benchmark_acceptance*.py`, this report, and evidence under `artifacts/benchmark_verification/`. No production backend/frontend files were edited by verification. Backend lead: `01a09b3d-0710-70d3-a709-4b647892e7b8`; frontend: `01a09b3d-790a-70a2-86a0-27e48790d491`.

## Recoverable baseline

Checkpoint: `artifacts/benchmark_verification/20260913T144913Z/`.

- `source_checkpoint.zip`: 108 source files; excludes secrets, datasets, virtual environments, logs, generated dependencies and artifacts.
- `source_manifest.json`: SHA-256 inventory of those files.
- `protected_engine_sha256.json`: 38 existing engine/reference/Launch files. Final reviewed differences are only additive `api.py` routing and coordinator-authorized `launch/job.py` nested source drift checks. `scripts/setup_launch.py` has the separately authorized recursive source-packaging fix. Scientific model/training/split/metric/validator code remains unchanged. Exact diff: `artifacts/benchmark_verification/authorized_source_changes.diff`.
- `historical_researcher.sqlite`: consistent SQLite backup obtained through a read-only source connection.
- `historical_rows.json`: per-row hashes and counts: 7 sessions, 31 experiments, 297 events, 62 ARIA messages, 0 final-evaluation freezes. Intermediate comparison: all completed-history rows unchanged. The pre-existing active session `wf-20260913-144606-5189` legitimately progressed from training to awaiting ARIA, and its exp-002 completed. Original events/messages remain; new worker events/messages were appended. Final preservation comparison passes with no historical violations; known in-flight progress is separately recorded in `artifacts/benchmark_verification/final_integrity.json`.

Both owners were notified of checkpoint readiness before their existing-file edits. The initial extension allowlist omitted `.mjs`/`.cjs`; the changed ESLint config is separately recovered from the frontend owner’s exact pre-edit tool output at `artifacts/benchmark_verification/original_eslint.config.mjs`. This sidecar preserves source text, not certified original line-ending bytes. Existing TypeScript/TSX/CSS and protected scientific code are in the original archive.

## Tests completed

| Check | Result | Scope |
|---|---|---|
| Existing offline baseline | 65 passed, 1 training test deselected, 44.57s | experiments, nudge, operations, audit fixes, API; isolated data/artifacts |
| Final combined nontraining regression | **162 passed, 1 training test deselected, 18.96s** | existing65 plus independent acceptance suites at stable checkpoint |
| Follow-up import recovery | 2 passed | queued requests do not start expiry; stale failure durable; late completion cannot replace terminal status |
| Independent Launch packaging checks | 4 passed, 3.62s | nested inclusion, non-source exclusion, fingerprint updates, changed/added/removed nested source rejection; all remote calls/dispatch intercepted |
| Independent storage/API/security suites (current integrated backend) | **93 passed, 17.36s** | 10 storage/readiness + 11 API + 72 security; isolated SQLite and intercepted worker dispatch |
| Real OpenML / GitHub adapters | Passed partial imports | tasks15/59; xView2 and EuroSAT repository metadata |
| Real DOI / Crossref paper adapter | Passed partial import | MedMNIST v2 title/date; no invented score/results |
| Real arXiv paper adapter | Failed safely |1709.00029 unavailable; no raw error/credential exposure; not claimed as live pass |
| Real-ARIA budget-one execution | **Passed independently** | completed connected/full-data run; scores, model files, producer identities, replay and11 Weave spans verified; no test evaluation |
| Real Hugging Face adapter search/import | Passed | authenticated search returned two WildfireIA matches; actual import completed with exact dataset pin and executable curated adapter |
| Actual local + remote Launch snapshot | Passed |47 Python files including10 nested benchmark files match; no Launch execution |

The 93-test result includes session-recovery security regressions and expanded provider tests. Passing mocks do not establish real ARIA liveness or execution. Existing two deprecation warnings concern Starlette/FastAPI test infrastructure.

Independent tests exercise migration preservation of old schemas and rows, immutable source-refresh snapshots, user-edit provenance, explicit result selection/context, concurrent idempotency, source conflicts, atomic rollback, missing/zero values, search/filter pagination, unique links, offline catalog/project creation, unsupported and altered protocol rejection, connected dispatch, repeated starts, partial imports, provider failure sanitization, URL/DNS safety, redirect rejection, response bounds, malformed payloads, and protected metadata edits.

Live HF evidence: `artifacts/benchmark_verification/live_hf_acceptance.json`. Exact observed revision: `cd1fcad871c4293ec7bf066229d8714f059d42de`. Provider credentials were read without printing their values. Current official [HF API](https://huggingface.co/docs/hub/api), [OpenML task](https://docs.openml.org/reference/tasks/), and [GitHub repository](https://docs.github.com/en/rest/repos/repos#get-a-repository) documentation was reviewed.

## Findings sent to owners

1. **Fixed and independently retested:** storing curated source identifiers changed casing and blocked the valid WildfireIA executor. Strict canonical comparison now accommodates normalized identities without losing pins.
2. **Fixed and independently retested:** readiness originally counted metric direction rather than split/script evidence. Six checks now cover dataset, metric, target, splits, repository and evaluation script. Missing split/script remains partial; complete metadata alone never grants an executor.
3. **Fixed and independently retested:** deterministic project session IDs could collide with a custom session created through the existing session API. Unlinked collisions now reject; linked retries verify connected/full-data settings and exact execution configuration. Security suite: 61 passed, including ten linked-session mismatch cases.
4. **Fixed and independently retested:** OpenML tasks sharing a dataset identity merged and overwrote task/evaluation protocol. Task imports now retain separate task identities.
5. **Fixed and independently retested:** malformed nested OpenML qualities/input names now receive safe handling rather than uncaught exceptions.
6. **Fixed and independently retested:** custom-session project snapshots initially advertised a mismatched research seed as executable; snapshots now preserve actual session settings/protocol and reject mismatches. Three new independent API checks pass.
7. **Fixed and independently retested:** abandoned imports older than ten minutes become a persisted safe failed state without changing saved metadata. Durable timing starts only after the provider lock is held, so queued requests do not expire. Late completions cannot overwrite terminal attempts. Retry uses a new import ID.

## Primary-source verification

Detailed sources and missing fields: `artifacts/benchmark_verification/source_evidence.md`.

| Candidate | Independently verified | Required caveats |
|---|---|---|
| WildfireIA | Live HF revision; public ungated data; official code metric/split; project page 53.3% XGBoost over five seeds | Dataset license `other`, code MIT; full seed list/date missing; validation cannot be compared with test reference |
| Healthcare breast-w / OpenML task 15 | Dataset 15 v1, target `Class`, 699 examples, stratified 10-fold x1 | Task declares **no metric**; no published target/model; OpenML `Public` and UCI CC BY4.0 are distinct source facts |
| xBD / xView2 baseline | Official paper/repository and challenge scoring | Paper weighted F1 0.2654 is not verified as challenge composite; dataset license/revision and fully matched result context missing |
| EuroSAT | 27,000 images, 10 classes; paper RGB pretrained ResNet-50 accuracy 98.57%, class-wise 80/20 | No frozen indices/seeds or paper-matched data revision; another model configuration gives a different result |
| OpenML Iris task 59 | Dataset61 v1, target `class`, 150 examples, predictive_accuracy, stratified10fold x1 | No single target/model; task folds are not a fixed train/validation/test partition |

The actual seeded SQLite catalog was independently compared with these primary facts: exactly five candidates, only WildfireIA executable, four partial; no xBD score or invented healthcare metric; EuroSAT keeps its explicit RGB/pretrained result and missing revision. Evidence: `artifacts/benchmark_verification/final_catalog_source_comparison.json`. Other datasets require an executor.

The WildfireIA PDF gap is resolved: the local 20-page paper matches the author-hosted and pinned-commit PDF byte-for-byte (SHA256 `faa0a4d656a143fd6c445662544eb1110a8d44a02c56ff337e27b6deb9528e49`). Visual inspection of pages6–8 confirms Table3 XGBoost .533±.003, five seeds, and chronological split; pinned summary code corroborates test designation. Exact numeric seeds remain absent.

Owner corrected xBD/EuroSAT mixed review notes to inferred curated provenance. EuroSAT dataset license remains conservatively null despite source evidence of MIT.

## Remaining acceptance

- Completed: session-recovery collision retest and live production HF/OpenML/GitHub/DOI reads. arXiv live availability remains a limitation.
- Completed: actual five-record catalog/evidence comparison and mixed-notes provenance correction.
- Completed: the coordinated real-ARIA validation-only run, project link, journal/replay, remote measurements/model files and producer provenance. No new official test evaluation.
- Frontend handoff received:14 tests/typecheck/lint/build pass; recorded journal and mobile empty/error/import views inspected. **Populated integrated browser acceptance remains pending** because automatic approval review rejected the isolated preview launch; parent prohibits workarounds. No real browser import/save/start claimed.
- Completed: protected-code and completed-history preservation comparison after integration; repeat only if subsequent production edits or live evidence warrants it.
- Actual reviewed project `81be53fa-fbef-4566-a654-65b4189055c1` was initially read through API8001 with budget1, exact pin and session null (`independent_reviewed_project.json`). It now links the completed verified session below. This is API acceptance; no populated browser acceptance is claimed.

Additional live API reads independently confirm the saved EuroSAT project `bfae7a2e-71c6-4d71-97fd-790106fe6e4f` retains its selected .9857 RGB result, is non-executable and has no session; persisted DOI import `import-677f99937c7447999f5f12878b5df7b8` is partial with no target. Evidence: `independent_live_partial_project.json`. The catalog now also includes the imported paper; the curated five-record subset remains the reviewed library.

Recaptured Launch job `wildfire-validated-local-step:v4` digest `752d3e854b4f4488dcd871e45497a8c1` references code artifact `code-wildfire-validated-local-step:v4`, digest `f38cdcfc9f05d9e787aae19c7fb0fdf0`. Independent live W&B manifest reads matched all47 Python files against the local stage, including api.py and all10 nested benchmark files; no missing/different entries. Evidence: `launch_snapshot_acceptance.json`, `remote_launch_snapshot_acceptance.json`. Job metadata and code artifacts are separate W&B artifacts; comparison used the referenced code artifact.

## Completed real-ARIA acceptance

After the prior worker completed, the backend lead started the reviewed budget-one project through API8001. Session `wf-20260913-150158-81be` completed with worker false, connected mode, seed553371, full train22576/validation7047, and no error.

| Experiment | W&B run | Validation AUPRC | Remote model digest |
|---|---|---:|---|
| exp-000 baseline | iqe0w3hn | 0.18417067640399878 | a16c248b48f2e6645bec4aee119337ae |
| exp-001 ARIA proposal | jt6bmlen | 0.39721230867438967 | bf3f9f6ca6d0ea2387d4ee7e516f0b28 |

Both finished remote run summaries match local measurements within1e-12. Both local model.joblib and manifest.json files match remote artifact manifest digests. Score labels are VALIDATION_AUPRC, split val(2019), benchmark_comparable=false. These results cannot claim to beat the published test reference.

Accepted proposal-r1:v0 digest `46be9aabf09712d9992d8520ac368a7e` was produced by run `fe26nc1a`, ARIA thread/turn `01a09b54-7e53-7591-8686-2fc8ebabcaf9`. Accepted decision-final:v0 digest `d04a07ccc1a3ca733337bb6e2e801b03` was produced by run `1eqsxsys`, ARIA thread/turn `01a09b56-3a99-7f22-aee9-11ef26daa04f`. Remote artifact digests match persisted accepted messages; both producer configs contain real `_wb_agent` identities.

Replay contains both experiments and identical scores; journal events count20. Existing read-only remote verifier also exited0/problems[]: execute_training2, evaluate_result2, publish_research_state2, receive_aria_output2, validate_experiment1, record_aria_decision2. No final_evaluation record or final-evaluation freeze exists for the acceptance session. Post-live protected/history comparison passes; only previously active historical session progress differs from initial checkpoint.

Evidence: `live_final_acceptance.json`, `live_final_api_evidence.json`, `live_model_file_comparison.json`, `post_live_integrity.json`, and reproducible read-only `verify_live_acceptance.py` under `artifacts/benchmark_verification/`. Existing remote-verifier output is also preserved by lead at `artifacts/benchmark_backend/lead_remote_verification.json`.

No verification-owned training worker or shared service was started or stopped; the backend lead owned the single authorized run. No official test evaluation ran. **Only populated integrated browser acceptance remains pending**; frontend should send its evidence after preview approval. Do not mark the overall feature accepted until that remaining gate is resolved.
