# Backend / integration handoff

Status 2026-09-13: implementation/provider gates 1–6, backend security/regression portion of checkpoint 7, and real-ARIA project execution/evidence completed. Only populated browser acceptance remains blocked on approved frontend launch. Do not describe all eight gates as complete yet.

## Ownership and boundary
Backend owns `wildfire_researcher/benchmarks/`, `scripts/import_benchmark.py`, `scripts/sync_benchmarks.py`, new benchmark owner tests, shared BENCHMARK_CONTRACT.md, and the additive router mount at the end of api.py. Scientific engine/reference modules are unchanged. Necessary Launch integration changes in `scripts/setup_launch.py` and `launch/job.py` preserve/cross-check nested Python sources; no execution behavior changes. Frontend owns pages/components/client; narrow Next distDir and CommonJS test lint configuration delegated to frontend. Verification owns acceptance tests and report.

Recoverable source and SQLite checkpoint: `artifacts/benchmark_verification/20260913T144913Z/`. Independent protected check reports exactly the authorized api.py mount and Launch packaging/drift-check changes. An existing active session progressed normally during work; completed history remains intact.

## Implemented
- Additive normalized SQLite tables for benchmark records, sources, source snapshots, field provenance, results, imports, projects and session links. Existing scientific tables untouched.
- Local-only catalog reads, search/filters/sort, explicit bounded refresh, durable partial imports, immutable reviewed project snapshots, explicit result selection and idempotency.
- HF discovery/import; OpenML dataset/task metadata with separate task identity; bounded GitHub metadata/README/root inspection; structured Crossref DOI and arXiv metadata import. No external repository code executes.
- Exact pinned WildfireIA adapter. Saved projects and Start Research are separate. Connected ARIA/full-data execution only, with existing worker and final-evaluation gates. Altered protocol cannot start. Existing unlinked session IDs are never adopted; linked sessions must match mode, data limits, seed, target, budget, project and full protocol.
- `/projects/from-session` links existing custom sessions into the same thin project model without changing or running them. Mismatched settings are retained and non-executable.
- Public access requires explicit evidence, not URL existence. Readiness, executor support and comparability remain separate. User edits never become source verification.
- HTTPS exact host allowlist, public DNS/IP pinning, no redirects or proxies, 15-second request deadline, 2MB bound, decompression disabled, sanitized errors and per-user credential retrieval. No credentials in browser, source metadata, or output.

## Actual curated catalog
Seeded with `python scripts/sync_benchmarks.py --curated`; all five live provider reads succeeded with no warnings. Independent `final_catalog_source_comparison.json` confirms:
- `wildfireia`: executable; pinned HF/code, AUPRC test reference .533, complete metadata. Published seed list remains undisclosed; validation does not beat a test reference.
- `openml-t-15`: breast-w healthcare, 699 instances, official ten-fold task, missing metric/target/model.
- `github-dc3a86534d39f2ebbf9235ea`: xBD/xView2, dataset registration/access and license unresolved, no conflated F1 target.
- `github-bf8562abea828eacc15ffca4`: EuroSAT, 27000 images, explicit pretrained RGB ResNet50 .9857 result with source/context; revision/frozen split/validation unresolved. Target stays unselected.
- `openml-t-59`: Iris150, predictive_accuracy task metadata, no invented published target.

## Verification evidence so far
174 final owner tests passed. Independent final nontraining acceptance and existing regression: 162 passed, one training test deselected; later targeted packaging/queue/terminal recovery checks also pass. Exact live evidence in `artifacts/benchmark_verification/`: HF, expanded OpenML/GitHub, DOI and final catalog source comparison. Crossref live succeeds; arXiv API timed out safely twice, so do not claim arXiv live success. API mock-dispatch verifies separate creation/start and journal/replay without training.

Actual API evidence `live_backend_acceptance.json`: EuroSAT selected-result project `bfae7a2e-71c6-4d71-97fd-790106fe6e4f` returns Start409/sessionnull; MedMNIST DOI partial import `import-677f99937c7447999f5f12878b5df7b8` is durable. The additional paper makes six catalog records while the curated subset remains five. Reviewed executable budget1 project `81be53fa-fbef-4566-a654-65b4189055c1` has no session yet. Saved snapshot evidence: `reviewed_live_project.json` and `independent_reviewed_project.json`.

Abandoned imports: the processing timestamp starts only once the provider lock is acquired. Fetching older ten minutes becomes a durable failed/retryable record on read. Every retry uses a new UUID; atomic completion cannot overwrite a recovered terminal record. Catalog evidence and project/session identities remain untouched.

Launch job `wildfire-validated-local-step:v4`, digest `752d3e854b4f4488dcd871e45497a8c1`, was recaptured without running a job or creating a session. Independent remote manifest comparison verified 47 Python files including all ten nested benchmark files. Fresh cloud agent heartbeat at15:06:56Z shows POLLING and stopPolling=false. Evidence `artifacts/benchmark_backend/live_launch_preflight.json`.

Official provider references consulted: HF Hub/OpenAPI and hf_api docs; OpenML REST/task reference; GitHub REST repository/contents/tree docs (API2026-03-10); Crossref REST and arXiv API manual. Source-specific evidence and uncertainties are in `source_evidence.md`.

## Running processes / final next actions
- Existing backend8000's pre-existing session `wf-20260913-144606-5189` completed naturally and its worker exited before acceptance began. It was not cancelled or repurposed.
- New backend8001: uvicorn process26468 (exec session39815), current final production code. Its one acceptance worker is complete/exited. It shares the existing SQLite path.
- The former frontend3000 has no listener at final check. Isolated `.next-benchmarks` production build passed, but frontend3001 launch was automatically rejected: `blocked by policy`. Coordinator requested user approval for the concrete preview launch; no alternate-port/shell/proxy bypass.
- Fresh Chrome W&B Automations UI confirms the existing generic ARIA automation and recent execution. SDK empty automation listing does not represent this ARIA UI state. Bridge session IDs match its required wf-date-time-hex4 format.
- Real-ARIA acceptance completed: project `81be53fa-fbef-4566-a654-65b4189055c1` links session `wf-20260913-150158-81be`, budget1, connected, full22576 training/7047 validation examples, seed553371. ARIA kept balanced logistic regression and expanded metadata to all permitted features; validation AP improved .1841706764 to .3972123087. ARIA final decision KEEP exp-001. No official test evaluation.
- Existing CLI replay export saved `artifacts/wf-20260913-150158-81be/replay.json`. Existing `scripts/verify_remote.py` exited0 with no problems, matching both finished measured runs, source/result artifacts and11 required linked Weave spans. Evidence `artifacts/benchmark_backend/lead_remote_verification.json`; independent final verification adds native ARIA producer identities. Journal path `/?session=wf-20260913-150158-81be`.
- Complete integrated browser populated catalog/review/save/unsupported/partial flow against the approved preview; await frontend + independent reports before completion claim.

Independent final backend live gate passed: both local model files and manifests match remote artifacts, both ARIA producers have native thread/turn identities, replay contains two experiments/twenty events, all eleven required Weave spans present, and post-live protected/history checks report no violations. `final_evaluation` is null and freeze table count remains zero. Final report: `BENCHMARK_ACCEPTANCE_REPORT.md`. Both frontend and verification sessions are ready to resume the sole remaining browser gate after preview approval.
