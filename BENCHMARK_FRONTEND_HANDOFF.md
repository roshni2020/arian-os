# Benchmark frontend handoff

Date: 2026-09-13. Owner task: 01a09b3d-790a-70a2-86a0-27e48790d491.
Backend/integration owner: 01a09b3d-0710-70d3-a709-4b647892e7b8.

## Status

Frontend implementation is complete against BENCHMARK_CONTRACT.md v1, including the additional source forms after the backend lead reported independent checkpoint 4 approval. Tests, TypeScript, lint and production build pass. **Integrated live benchmark browser acceptance remains pending** because starting the isolated preview was rejected by automatic approval review. Do not call the overall feature accepted on this handoff alone.

## Implemented

- `/benchmarks`: live cached backend catalog, search, source/domain/task/metric filters, sort, pagination, explicit bounded Hugging Face refresh, stale-cache and provider-error notices, missing metadata, source badges and separate metadata/executor states.
- Catalog, details and saved project explicitly display dataset/repository public-access evidence. A source URL alone never displays confirmed public access; false means restricted, null/missing means access not confirmed. These fields are not user-editable verification claims.
- `/benchmarks/[id]`: source provenance beside fields, dataset revision, evaluation protocol, leakage restrictions, resources, reported result definitions/direction/dataset/revision/split, metadata completeness, executor compatibility and comparability.
- `/benchmarks/[id]/review`: editable imported fields, budget validation, explicit selection among multiple results, missing fields preserved, selected-result prefills distinguished from user corrections, source verification labels, stable idempotency key for an unchanged request retried within the page. Create project saves a snapshot and never calls Start.
- `/benchmarks/import`: Hugging Face, OpenML task/dataset, GitHub and paper/DOI entry forms. Requests use only the backend URL import endpoint. Partial/failed import warnings remain visible. No fake extraction-stage progress or fabricated results.
- `/benchmarks/imports/[id]`: persisted import status and continue-review links.
- `/projects` and `/projects/[id]`: saved specifications, immutable snapshot values and saved provenance, user corrections, selected result context, compatibility reasons, disabled unsupported execution, explicit Start Research, safe local journal URL handling, and direct links for already linked sessions without posting Start again.
- Existing Console: minimal benchmark/custom/project navigation and `?session=` selection support. Existing journal, replay, evidence, controls and engine behavior preserved. Custom entry opens existing manual WildfireIA setup; backend lead explicitly confirmed this scope because arbitrary private-dataset execution does not exist.

## Ownership / files

New frontend code:

- `frontend/src/app/benchmarks/**`
- `frontend/src/app/projects/**`
- `frontend/src/components/benchmarks/{BenchmarkShell,Catalog,BenchmarkDetails,ReviewImport,SourceImport,ImportStatus,ProjectOverview}.tsx`
- `frontend/src/lib/benchmarks.ts`
- `frontend/src/lib/benchmark-review.ts`
- `frontend/tests/benchmarks-client.test.cjs`
- `frontend/tests/benchmark-review.test.cjs`

Existing files changed:

- `frontend/src/components/Console.tsx`: Link import, session query selection, entry-point navigation, setup anchor only.
- `frontend/eslint.config.mjs`: lead-delegated narrow CommonJS test rule override; isolated generated build directory ignored.
- `frontend/next.config.ts`: lead-delegated optional `NEXT_DIST_DIR` override, default stays `.next`.
- `frontend/tsconfig.json`: Next automatically added `.next-benchmarks/types/**/*.ts` and `.next-benchmarks/dev/types/**/*.ts` include paths and reformatted JSON during isolated build. Backend lead notified.

No backend, contract, implementation plan, protected scientific modules, migration tables, credentials, existing journal components, or historical records edited by frontend. Source checkpoint was confirmed by verification before Console changes: `artifacts/benchmark_verification/20260913T144913Z/source_checkpoint.zip`.

Verification later identified that its checkpoint allowlist omitted `.mjs`/`.cjs`. At its request, original ESLint source text from the pre-edit tool read was preserved in `artifacts/benchmark_verification/original_eslint.config.mjs`. This is text recovery, not a byte-original checkpoint; its SHA256 is `870F1ADCCECF3051CBCD9FD307CEF51D7633CF510979C181A81F4B1797273493` and must not be described as the pre-edit file hash.

One authorized specialist subagent owned API types/client, project pages and their tests. Parent integrated catalog, details, review, source imports and navigation.

## Validation

From `C:/AI/Projects/focus/frontend`:

- `npm test`: **14 passed, 0 failed**. Covers existing replay, query encoding, create-vs-start separation, partial import success, backend errors, local journal URL filtering, saved snapshot/correction/provenance rendering, already-linked direct navigation, selected-result prefills without false corrections, explicit access evidence, missing values, zero target, invalid numeric target and JSON protocol validation.
- `npx tsc --noEmit`: passed; final Next production build also ran TypeScript successfully.
- `npm run lint`: passed across the full frontend. Existing CommonJS replay tests previously failed the TS require-import rule; the lead delegated the narrow test-file exception.
- `npm run build` with `BACKEND_URL=http://127.0.0.1:8001` and `NEXT_DIST_DIR=.next-benchmarks`: **passed**, all nine routes emitted (including root/not-found counting conventions in Next's route table). Output is under `frontend/.next-benchmarks`.

Browser checks performed with the already-running `http://localhost:3000` only, using CUA browser controls:

- Desktop benchmark catalog and backend-error state render in existing paper/ink/teal/rust journal styling.
- Catalog and source import page inspected at 390 × 844; single-column controls and navigation fit the viewport. Temporary viewport override reset afterwards.
- Source selector changes Paper URL/DOI label and input correctly; no import request submitted.
- Existing recorded journal `wf-20260913-104003-2c71` loads with 13 entries and unchanged historical evidence.
- `/?session=wf-20260913-123756-7824` selects that completed session with its three journal entries, confirming the project-style journal deep link.
- Benchmark catalog on port 3000 currently shows backend `Not Found`, expected because its existing backend target remains port 8000 without new routes. This is **not** live benchmark catalog acceptance.

All actual UI code calls real backend providers; fixtures appear only in tests. No source import/project creation/Start API was called by this frontend session during browser checks. No training or final evaluation was initiated.

## Preview blocker and running services

Existing frontend port 3000 / PID 20080 remains running. Existing API port 8000 owns an active research session; parent explicitly prohibited restart. Backend lead launched isolated API port 8001. Frontend session did not stop any shared service. No frontend process remains running on port 3001 from this session.

Attempted second `next dev --port 3001` exited because port 3000 already holds the same-directory Next dev lock. This led to the lead-delegated isolated output option.

Automatic approval review rejected a combined production build/start command, then also rejected the separately coordinated isolated start command. Exact latter command:

```powershell
$env:BACKEND_URL='http://127.0.0.1:8001'
$env:NEXT_DIST_DIR='.next-benchmarks'
npm run start -- --port 3001
```

Tool reported only `CreateProcess ... Rejected(... rejected: blocked by policy)`, with no more specific reason. Parent and backend lead received the exact rejection. Parent explicitly instructed no alternate shell/port/background launch or proxy rewrite workaround. No further launch was attempted. The isolated build itself succeeded.

## Exact next acceptance task

Latest lead update: real-ARIA acceptance session `wf-20260913-150158-81be` completed and was independently verified, with validation AP approximately `0.18417 → 0.39721`; replay export, models and provenance were verified and no test evaluation ran. Both backends were reported to have no active workers. This is backend acceptance evidence reported by the integration lead, not frontend browser verification. The static frontend build remains unchanged. Remaining gate: populated catalog/review/save/partial/unsupported flows and the completed acceptance journal in an approved, reachable browser preview.

Follow-up: lead requested read-only verification of acceptance session `wf-20260913-150158-81be`. Browser navigation to `http://localhost:3000/?session=wf-20260913-150158-81be` returned `net::ERR_CONNECTION_REFUSED`. A read-only listener check confirmed no listener on 3000, while 8000 (PID 14516) and 8001 (PID 26468) were listening. The earlier 3000 service status above is historical, not current. No service restart or alternative preview launch was attempted. This acceptance session's live/completed journal browser verification remains pending a reachable authorized frontend.

After parent/user resolves an authorized preview mechanism, connect a frontend preview to the updated backend without restarting API 8000 while its research session is active. Reuse the isolated build or rebuild after any later frontend/backend contract changes. Do not silently work around the rejected start action.

Then browser-verify: real catalog search/filter/refresh; WildfireIA details and pinned evidence; review and save project without starting; snapshot provenance and user corrections; explicit multiple-result choice; partial import from supported sources; unsupported/altered project disabled Start; persisted import continuation; provider failure and retry; keyboard navigation and populated mobile cards/review. Any real Start action belongs to the integration lead's coordinated bounded real-ARIA validation-only acceptance, never official test evaluation. Report findings to frontend owner and update this handoff after integrated browser acceptance.

## UI redesign — 2026-09-13

Replaced the paper-styled card grid with a neutral research workspace: persistent navigation, a compact benchmark list, source tabs, search, optional filters, and clear published-result/execution columns. Added responsive page layouts and shared buttons, fields, status labels, focus states and reduced-motion support. Detail, review, import, saved projects and the research journal now share this visual system. Extensive provenance remains available through disclosures; scientific execution and API payload behavior are preserved.

Live preview is running at http://localhost:3000/benchmarks and its benchmark API responds with the real catalog. Desktop/mobile browser checks covered populated catalog, source filtering, empty search/reset, review, source selector, project list and unsupported Start disabling. Research journal rendered the existing recorded session with separate validation and official-test metrics. No training, source import or project creation was performed during this redesign. The user's later 'train again' wording was clarified to mean that credits were reset, so no new run was started.

Also corrected catalog rendering of a single published result when no project target is selected, and replaced the nonmatching generic paper source filter with actual Crossref/arXiv provider tabs.

Validation: full frontend lint, all 14 tests and isolated production build passed. Production output `.next-benchmarks` uses BACKEND_URL=http://127.0.0.1:8001; the existing development service was neither stopped nor relaunched.

## Experiment analysis release — 2026-09-13

Implemented the approved next release in the research journal:

- Compare: persistent baseline/candidate selectors, metrics and signed deltas, nested configuration differences, precision–recall overlay with recorded-point tables, and AP/runtime views. Full records are fetched through the existing experiment endpoint because session summaries omit PR curves. Known matching session, score kind, split, seed and sample counts are required for deltas. Thresholded metrics explicitly use each run's own threshold.
- Error analysis: confusion matrices, all recorded subgroup rows, dimension/search/sort controls, and aligned baseline/candidate differences. Missing groups and mismatched group sample/positive counts never become zero or receive computed changes. Historical runner summaries are capped, so this view cannot recover groups not stored in those records.
- Execution: new read-only `/api/sessions/{session_id}/execution-status` endpoint and polling panel with transport, stored activity timestamps, scoped local worker observation, budget, feedback, events, W&B links, and existing Resume/Cancel actions only when applicable. `last_activity_at` and activity age refer to the same event/message timestamp. W&B Launch queue status and agent heartbeat remain explicitly unverified; the endpoint makes no remote requests.
- Navigation: Overview/Compare/Error analysis/Execution tabs with keyboard navigation and `?session=...&view=...` deep links. Linked projects expose the three new views. Custom session setup collapses by default. Replay uses stored visible records only, suppresses live execution controls, and does not hydrate from live caches. In-flight details cannot leak across sessions.

Validation: 43 frontend tests passed, full frontend lint and production build passed. Backend specialist ran 50 offline execution/API/Launch-packaging checks successfully; the existing training test was explicitly excluded. Browser checks against the completed acceptance and Launch sessions verified recorded metrics, actual PR curves, configuration changes, subgroup filtering/sorting, unknown remote health, and replay controls. Mobile comparison/error pages fit 390x844 with no document overflow, and the four tabs fit the available width. No training or final evaluation was initiated.

Runtime: development frontend remains on port 3000. After verifying all nine sessions were terminal and no local worker was alive, the idle API on port 8000 was restarted to load the endpoint (PID 25396 at restart). API 8001 was left untouched. Latest isolated production build under `.next-benchmarks` now targets API 8000. Python source changes invalidate older immutable Launch captures as intended; use the existing source recapture/package workflow before a future Launch dispatch. No package validation guard was bypassed and no remote artifact was written for this release.
