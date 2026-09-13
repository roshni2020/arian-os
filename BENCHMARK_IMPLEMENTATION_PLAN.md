# Benchmark discovery/import implementation plan

User authorized implementation, multiple sessions and specialist agents on 2026-09-13, after live credential tests. Full product brief: C:/Users/aliam/.codex/attachments/3359b5c8-25bb-4e8f-a204-8c1364ed8438/pasted-text.txt. Read it as product requirements subject to the boundaries below.

## Non-negotiable boundary
Add discovery/import above the working WildfireIA engine. Do not change scientific behavior, ARIA selection, validators, training, splits, metric implementations, final-evaluation gates, historical SQLite records or evidence. Additive API integration only. Preserve Automation/artifact and Launch execution. Real ARIA remains the researcher. No generic LLM replacement.

Current application has sessions, not a generic ResearchProject or arbitrary-dataset execution. Add one thin shared project model with links to existing sessions. WildfireIA is executable; other benchmarks may be discovered/imported but require a supported executor before running. Distinguish metadata completeness, executor compatibility, and benchmark comparability. Project creation saves a snapshot; Start Research is a separate action. Preserve research journal design.

## Eight checkpoints, in dependency order
1. Audit current architecture and tests; preserve recoverable code checkpoint; define protected files and contracts.
2. Add benchmark/source/provenance/result/import/project/session-link storage and migrations; shared page/API contracts. Benchmark results must retain dataset revision, metric definition/direction, split and model. Keep user edits distinct from source verification.
3. Real Hugging Face connector, backend cache/refresh/search, /benchmarks catalog, filters and honest partial states; sync CLI.
4. WildfireIA vertical slice: details, review, project creation, strict pinned-protocol compatibility and bridge to existing session creation/journal. Unsupported or altered protocols cannot execute. Verify before expanding providers.
5. OpenML task/dataset and GitHub URL connectors with provenance, bounded source inspection, deduplication and CLI imports.
6. Paper URL import, explicit multiple-result selection, and five verified curated examples (WildfireIA, healthcare classification, disaster damage, remote sensing, OpenML tabular). Missing values stay missing. Use supported structured sources first, no general crawler.
7. Integration/resilience/security/UX regression checks: stale cache, outages, missing fields, duplicate requests, interrupted import, user edits, SSRF/redirect/size/timeout limits, credentials, keyboard/mobile layouts, protected-engine integrity.
8. Live acceptance: real provider reads, reviewed WildfireIA project, one bounded real-ARIA validation-only execution, existing journal/replay/evidence, unsupported benchmark and partial import flows. No new official test evaluation. Publish test report and handoff.

P1 excluded for now: Kaggle (explicitly not needed), generalized executors, richer leaderboard extraction, recommendations. Do not label non-runnable imports ready to execute. No invented headroom or unverified dates/scores/licenses. No repository execution during import, no credentials in frontend/source/logs. External requests backend-only; cache, bound requests and respect rate limits. Use existing local Python/SQLite/Next.js and W&B stack; no new paid services required.

## Concurrent session ownership
Backend/integration lead: owns benchmark backend package, schema, migrations, shared contract document, new API routes and necessary additive mounting, project-to-session bridge, backend/provider CLIs. Sole authority for protected API wiring and migration application. Coordinates checkpoint gates and live execution. May use up to 3 bounded specialist subagents on disjoint files.
Frontend session: owns new benchmark/project frontend pages/components/client and minimal navigation integration. Preserve existing journal and evidence. Read frontend/AGENTS.md and installed Next docs. No backend or contract changes without coordination. May use bounded UI/test subagents on disjoint files.
Verification session: owns independent new acceptance/security/regression tests, protected-file baseline/checkpoint, provenance verification and acceptance reports. Does not change production backend/frontend files; send findings to owners. May use bounded audit/source-validation subagents. Do not run expensive integration tests or training concurrently with live training; coordinate with lead.

There is no root Git repository. All sessions use the same saved local workspace, so file ownership is mandatory. Preserve existing user changes, do not initialize or move unrelated repos. Avoid concurrent edits to shared contracts, configs, manifests, migration tables and services. Lead owns shared contract changes; frontend tests stay frontend-owned; verification tests use tests/test_benchmark_acceptance*.py. Do not stop shared services or run benchmark sessions without coordinator agreement.

## Handoffs and contracts
Lead publishes BENCHMARK_CONTRACT.md before dependent implementation and creates BENCHMARK_BACKEND_HANDOFF.md. Frontend publishes BENCHMARK_FRONTEND_HANDOFF.md. Verification publishes BENCHMARK_ACCEPTANCE_REPORT.md. Record checkpoint completed, file ownership, tests/results, sources, remaining work, blockers, running processes and exact next task. Re-read current files before editing because other sessions may be active. Source refresh cannot silently change saved project snapshots.

## Credentials, already tested live
Hugging Face authenticated and WildfireIA/search reads passed. OpenML provided key passed while invalid control was rejected. GitHub CLI already authenticated as ali-amjad52114; no browser login needed for backend. W&B existing user credential reads project. Keys are in Windows per-user environment (HF_TOKEN, OPENML_API_KEY, WANDB_API_KEY); fresh processes may need reading HKCU Environment, as existing config.load_wandb_credential does. Never print keys. No need to request keys again. Recheck current official provider docs when implementing endpoints. ARIA/Launch must be checked before live acceptance; do not infer current liveness from past runs.
