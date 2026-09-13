# ARIA product expansion: multi-agent, multi-session implementation plan

Prepared 2026-09-13. Implemented after the user explicitly requested implementation and testing. See docs/aria-expansion/IMPLEMENTATION.md and the eight milestone handoffs for delivered scope, checks, and remaining limits. This plan alone does not authorize new paid training, sealed-test evaluation, or publishing.

## Outcome

Connect the existing research workspace to six ARIAca workflows: ask about selected experiments; propose an experiment from an error group; design a study before starting; verify improvements; retrieve findings across sessions; and produce a final evidence-backed report.

Use eight implementation work sessions, each ending with an independently reviewable result and a durable handoff. These are development sessions, not eight training runs. Use a lead and up to three specialist coding agents per work session. They are separate from the runtime W&B ARIA agent. No new Codex tasks need to be created until execution is requested.

## Existing foundation and constraints

- `wildfire_researcher/aria_client.py`: proven asynchronous Automation/artifact exchange. It is not a direct chat API. New analysis requests need a verified transport path.
- `loop.py`, `experiments.py`, `state.py`: structured proposals, revision checks, fixed baseline, bounded capabilities, KEEP/REJECT, final recommendation, duplicate-config prevention and durable history.
- `launch_step.py`: separate Launch execution path with validated actions. The local execution lock is not a distributed scheduler.
- Frontend `ResearchAnalysis`, `ExperimentComparison`, `ErrorAnalysis`, `ExecutionPanel`: real recorded data, comparison controls and execution status already exist.
- `final_eval.py`: freezes the recommended configuration and five predeclared seeds, records integrity and prior test exposure. It currently does not certify benchmark superiority.
- `runner.py`: accepts a seed and saves validation predictions; the main research loop nevertheless uses one session seed and disallows duplicate configurations.
- `agent_evals.py`: contract, grounding and decision checks already exist. Its fixed seed-noise threshold is a heuristic, not measured reliability for a new study.
- `scripts/publish_operations_followup.py`, `complete_workspace.py`, `promote_winner.py`: useful reporting/registry foundations, currently tied to historical artifacts and runs.

Do not redesign the existing executor or add OpenML execution in this release. Planning may describe unsupported tasks, but execution must remain explicitly unavailable until an executor supports them.

## User journey

1. Review a benchmark and ask ARIA to draft a study. See the fixed protocol, proposed experiments, success criteria and budget before choosing Start.
2. In Compare, select runs and ask a question. Receive an asynchronous answer with links to exact evidence and explicit unknowns.
3. In Error analysis, select a group and request an experiment proposal. Review expected benefit, tradeoffs and configuration changes before scheduling anything.
4. For a promising candidate, review a bounded verification plan using repeated validation seeds and/or ablations. Run it separately from discovery experiments.
5. While proposing or planning, ARIA can retrieve eligible previous findings, including failed ideas and contradictory evidence.
6. Review a report draft containing the study, decisions, verification, limitations and model references. Export locally or explicitly publish to W&B.

Asking, planning, proposing, verifying and starting are distinct actions. Draft creation never starts training. A finished historical session is not silently reopened by a question or draft.

## Agent organization and file ownership

| Role | Responsibility | Ownership rule |
| --- | --- | --- |
| Lead / integration | Contracts, sequencing, migrations, route registration, shared navigation, integrated acceptance | Sole editor of `api.py`, `state.py`, shared contracts, Console navigation and migration entry points during each session |
| Backend specialist | Request transport, domain services, workers, retrieval or report generation | Own a named new module/package and its focused tests; propose shared-file edits to lead |
| Product/UI specialist | The user-facing workflow, typed clients, loading/error/replay states, accessibility | Own named new components/pages; coordinate shared CSS/navigation with lead |
| Evidence/QA specialist | Scientific validity, concurrency/recovery tests, ARIA output evaluation and release checks | Own named test/fixture files; independently review claims and side effects |

Keep at most four agents active, including the lead. Freeze the contract before backend and UI implementation diverge. Separate worktrees are preferred when Git is available; otherwise use explicit disjoint file ownership. Do not allow simultaneous writers to SQLite, shared runtime services, or generated build directories. The lead alone coordinates any required service restart after checking active work.

## Shared architecture to settle in Session 1

Proposed new package: `wildfire_researcher/assistant/`, with separate contracts, storage, evidence, transport and service modules. Names below are proposals, not existing APIs.

### Durable records

- `EvidenceSnapshot`: immutable project/session/experiment identities, record revisions, dataset/protocol/config fingerprints, score kind and split, selected subgroup keys, allowed metrics and artifact digests. Distinguish validation from official-test exposure. Exclude credentials, raw personal data and arbitrary log dumps.
- `AssistantRequest`: request ID, kind (`ask`, `error_proposal`, `study_plan`, `report`), project/session scope, snapshot ID/hash, question/constraints, idempotency key, attempt/lease, timestamps, transport provenance and status.
- `AssistantResponse`: request ID, snapshot hash, schema version, structured answer/draft, citations to supplied evidence IDs, assumptions, missing evidence and validation outcome. Store actual ARIA artifact provenance; do not label a generic LLM response as ARIA.
- `ExperimentDraft` and `StudyPlan`: immutable versions, capability/plan hash, origin request and evidence, proposed configuration, primary objective, secondary criteria, estimated rather than guaranteed cost/time, approval/start state.
- `VerificationStudy` and child runs: frozen comparison/seed/ablation plan, separate compute budget, resumable per-run identities, validation-only results, and aggregate evidence.
- `ResearchFinding`: source experiment/request/verification references, protocol fingerprint, scope, outcome, limitations, eligibility and supersession links.
- `ReportSnapshot`: frozen evidence set, template/prompt version, narrative, computed tables, validation/verification/test sections, local export and optional publication record.

### Request lifecycle and boundaries

Use `queued -> dispatched -> waiting -> succeeded`, with explicit `failed`, `timed_out` and `cancelled` outcomes. Responses arriving after cancellation must not trigger further actions. Use atomic claims, compare-and-swap transitions, a durable dispatch outbox, bounded retries and durable idempotency; process memory alone cannot prevent duplicate work after restart. Reconcile ambiguous external dispatches before retrying. Do not promise exactly-once delivery from W&B; make response consumption and consequential actions idempotent.

Prototype a separate non-training trigger and unique request/response artifact namespace. Existing research Automations must not match these requests or ARIA upload runs. Do not put a question into `<session>-proposal-r<N>` or overwrite the active research state's `latest` artifact. Concurrent questions must retain independent snapshots, even if a study advances while an answer is pending.

Proposed resource APIs: create/read/cancel assistant requests; list request history; create/version/approve experiment drafts and study plans; start/read/cancel verification studies; search eligible findings; create/read/export/publish reports. GET requests have no side effects. POST actions have idempotency and explicit scope. Response citation validation is server-side.

Prior official-test results must never enter future hypothesis generation through chat history, retrieval or reports. Classify requests by purpose. Historical report review may display test results, but that conversation and its findings are ineligible as future discovery context. Filtering alone does not erase the project's existing test exposure; keep the current exposure and claim-eligibility restrictions.

## Implementation sessions

### Session 1 — Contracts, evidence snapshots and ARIA transport proof

**Deliverable:** agreed v1 schemas, additive migrations, evidence builder and a real non-training ARIA request/response proof.

- Lead: inventory existing state and Automations, freeze contracts, assign paths, define purpose/exposure rules and migration compatibility.
- Backend: implement request persistence and immutable evidence snapshots; prototype dedicated dispatch/polling with request IDs, timeouts and artifact provenance.
- UI: define the request-status and evidence-citation components against fixtures; establish where Ask, Propose, Plan, Verify and Report appear without changing the working analysis layout.
- QA: test duplicate submissions, stale/wrong-scope outputs, malformed citations, restart recovery, test-data exclusion and nonmatching Automation names.

**Gate:** one real ARIA answer to a bounded recorded-data question, with a retrievable output artifact and valid request/snapshot IDs, and zero training jobs. Verify the currently available W&B trigger capability rather than assuming a public chat API. If the transport cannot be established, record the exact blocker; keep UI capability-gated and continue independent local contracts/tests without presenting fixtures as live ARIA.

### Session 2 — Ask ARIA about selected runs

**Depends on:** Session 1.

- Backend: request creation/history/cancellation and answer validation; selected-run evidence includes actual configurations, metrics, thresholds and available subgroup summaries. Persist each follow-up's evidence snapshot and bounded conversation context.
- UI: an Ask ARIA panel launched from Compare or experiment details, prefilled with selected runs. Show queued/waiting/failed/answered states, scope, citation links and missing evidence. Preserve the answer's original selections when the user changes the current comparison.
- QA: assess whether numeric statements map to exact fields or approved computed differences; reject fabricated references and distinguish observation from causal speculation. A number appearing somewhere in the snapshot is insufficient: verify its run, group and metric path. Test rapid session switching, concurrent questions and replay. Replay may show stored answers but must not silently dispatch new requests.
- Lead: integrate routes, request history and feature gating.

**Gate:** ask why aggregate results improved while a selected region regressed; answer cites the correct runs and regional counts, notes each run's threshold, and never invents omitted groups or claims causality from a comparison alone. Asking cannot alter training history or budgets.

### Session 3 — Turn an error group into a reviewed experiment

**Depends on:** Sessions 1–2.

- Backend: versioned draft service; translate a selected group and run comparison into an ARIA request with hypothesis, one proposed change, primary/secondary criteria, expected tradeoffs and unresolved evidence. Validate against the existing capability manifest.
- UI: “Propose experiment” from a group row; show the source evidence, configuration diff, expected benefit and reviewed budget. Provide edit/revise and explicit schedule/start actions.
- QA: test small/missing groups, different thresholds, unsupported configs, duplicate configs, stale drafts and double scheduling. Distinguish correlation-based hypotheses from demonstrated mechanisms.
- Lead: define a safe admission point. An active study can accept a reviewed suggestion only at a valid revision/checkpoint, without racing its autonomous proposal. A completed study creates a linked follow-up study; its historical recommendation remains unchanged.

**Gate:** a cited subgroup finding becomes a valid reviewable draft; draft creation runs nothing. A separately authorized bounded execution starts exactly once, retains provenance and records how its admission interacted with the autonomous loop. If the session changed, revalidate/review rather than silently applying the old draft.

### Session 4 — Plan a study before starting

**Depends on:** Sessions 1 and 3. Can be developed alongside Session 5 after the shared contracts are stable, subject to the four-agent limit.

- Backend: plan generation from a saved benchmark/project snapshot and supported executor capabilities; versioned success criteria, experiment-count and compute limits, stopping conditions and adaptive next-step rules.
- UI: Plan -> Review -> Start on the project page. Explain the fixed baseline separately from ARIA-proposed experiments. Clearly mark unsupported executors and uncertain estimates.
- QA: validate budgets, metrics, split restrictions, stale project snapshots and idempotent plan-to-session creation. A changed plan invalidates previous start approval.
- Lead: integrate plan identity into session creation. Preserve the fixed WildfireIA baseline/protocol; ARIA can explain that baseline but cannot silently replace it. Future selectable baselines require an explicit executor capability.

**Gate:** a valid approved plan starts one supported session and records the exact plan hash. Saving or revising a plan never starts execution. The sequence is an initial research strategy that can adapt to evidence within the approved limits.

### Session 5 — Verify improvements without consuming the test set

**Depends on:** Sessions 1 and 3; uses the budget contract from Session 4 if available.

- Backend: separate verification ledger and resumable scheduler. Freeze baseline/candidate configs, paired seed list, dataset/split, comparison method, ablation variants and total child-run budget before execution. Reuse the training primitives with explicit per-run seeds and separate artifact directories.
- UI: “Verify improvement” from Compare; preview the run count and evidence sought, then show per-seed results, paired differences, spread, failures and ablation outcomes.
- QA: test duplicate child-run claims, interruption/resume, missing seed pairs, mismatched datasets, selective-result omission and cancellation. Assert no sealed-test loader is called. Verify runtime locking with existing local and Launch execution.
- Lead: keep verification out of discovery iteration counts, unique-config constraints and numeric-best bookkeeping. Do not weaken existing proposal deduplication to accommodate repeated seeds.

**Gate:** an authorized bounded validation-only study resumes without duplicate training; results disclose all planned/completed/failed runs. Seed variability is measured, not inferred from the fixed agent-evaluation heuristic. Paired seed results describe training variability on this validation set; they do not establish generalization, causal effects or benchmark superiority. If a model is deterministic under the tested setup, report that repeats provide limited evidence. Ablations change one declared component where feasible.

### Session 6 — Retrieve evidence across research sessions

**Depends on:** Sessions 1–3 and 5 for verified-finding ingestion; historical unverified findings can be indexed earlier with explicit status.

- Backend: structured finding extraction and retrieval. Start with SQLite metadata filters and text search; add embeddings only if retrieval evaluation demonstrates a need. Match dataset/revision, task, metric, split, features, executor and protocol before ranking.
- UI: “Related findings” in Ask/Plan/Propose, with positive and negative outcomes, source links, age and verified/unverified labels. Display why a finding is relevant and let the user exclude it.
- QA: evaluate relevant retrieval, protocol mismatch, duplicates, contradictory findings, source deletion/unavailability and scope isolation. Exclude fallback fixtures, test-exposed narratives and unsupported comparisons from scientific planning context.
- Lead: inject a bounded, snapshotted retrieval set into new requests. New findings cannot retroactively change the evidence behind an existing answer or proposal.

**Gate:** a new proposal can cite a relevant prior failed idea and explain whether a changed condition justifies revisiting it. Test-result text cannot leak into hypothesis generation. ARIA recommendations remain reasoned choices rather than a blanket ban on every previously rejected configuration.

### Session 7 — Final research report and model handoff

**Depends on:** Sessions 1–2 and 5; Session 6 supplies optional cross-study context.

- Backend: refactor existing report scripts into parameterized services. Build deterministic metric tables from a frozen evidence snapshot; use ARIA for the cited narrative. Include objective, protocol, experiments, KEEP/REJECT reasoning, verification, limitations, recommendation and existing model/artifact references.
- UI: Report draft -> Review -> Export or Publish. Include validation and verification sections; include official-test results only when already available and clearly separated. Show absent tests, missing artifacts and publication failures honestly.
- QA: test numerical reconciliation, missing evidence, report immutability, replay, safe rendering, idempotent publish/retry and explicit handling of W&B API incompatibility. Keep report text with test exposure out of future discovery retrieval.
- Lead: preserve final-evaluation freezing and claim rules. Generating a report neither runs final evaluation nor promotes a model. Registry promotion is a separate explicit operation; existing artifact availability is verified first.

**Gate:** local report is readable and matches stored evidence before external publication. Publishing occurs once when explicitly requested, with read-back verification and retry reconciliation. Reconstructed models remain labeled as reconstructed rather than presented as original fitted artifacts. A later report is a new version, not a silent rewrite of the earlier evidence set. W&B's Reports API is in Public Preview, so isolate the adapter and retain a local export fallback.

### Session 8 — Integrated acceptance and release

**Depends on:** Sessions 2–7.

- Lead: integrate, check migrations and runtime capabilities, sequence any service changes, finalize release notes and rollback instructions.
- Backend: exercise worker/request restart, retry, cancellation, budget accounting and duplicate-event handling against a test database.
- UI: verify the complete journey, empty/error/loading states, keyboard operation, mobile layout, stable selections and stored replay.
- QA: run contract and integration suites, evidence-grounding evaluation, cross-session leakage tests, existing benchmark/protocol/final-eval regressions and source-package checks.

**Gate:** demonstrate Plan -> explicit Start -> Compare -> Ask -> group proposal -> explicit verification -> related findings -> report review/export. Use fixtures for most failure paths and a small explicitly scoped real-ARIA acceptance run only when execution is authorized. Record request IDs, artifact digests, run IDs, measured costs where available, test output and screenshots. Unsupported or unverified capabilities remain disabled rather than simulated. Recapture changed immutable Launch source packages through the existing workflow before dispatch; never bypass package validation.

## Dependencies and release cuts

Critical order: S1 -> S2 -> S3 -> S5 -> S6 -> S8. S4 follows S3 and can proceed independently of verification implementation; S7 follows S5 and can proceed alongside S6 using its own session evidence. Parallel development must still respect file ownership and the four-agent ceiling.

- Release A: Sessions 1–2, cited questions about recorded runs.
- Release B: Sessions 3–4, reviewed proposals and study plans.
- Release C: Sessions 5–6, verification and reusable research evidence.
- Release D: Sessions 7–8, reviewed reports and integrated acceptance.

Treat a session as a deliverable boundary, not a promise that it fits one model context window or a fixed number of hours. Session 1 determines transport effort; verification and concurrency are the largest implementation risks. Do not estimate calendar delivery before that gate.

## Handoff and resumption protocol

At the end of each session, write `docs/aria-expansion/session-N-handoff.md` with: completed scope; changed files and owners; schema/API versions; exact test commands/results; request/artifact evidence; remaining risks; current service/worker state; feature flags; and the next bounded task. Add a migration note and test database snapshot where needed. Never include secrets.

The next lead reads this plan, the preceding handoff, applicable AGENTS.md and relevant installed Next.js documentation before changing frontend code. Verify current service state rather than trusting old PIDs. Resume outstanding tasks; do not rerun paid experiments simply to regain context.

Reusable implementation-session prompt:

> Execute Session N of ARIA_MULTI_SESSION_PLAN.md. Read its dependencies and previous handoff first. Use a lead plus up to three agents with disjoint file ownership. Implement and validate this session's deliverable, preserve existing scientific and execution safeguards, and document the result in docs/aria-expansion/session-N-handoff.md. Draft/analysis actions must not start training. Do not launch paid training, sealed-test evaluation or external report publishing unless separately authorized for a concrete bounded action. Surface a failed transport or compatibility gate honestly; never substitute fixtures or another model as live ARIA.

## Success measures

- Every accepted response has matching request/snapshot identities and resolvable evidence citations.
- Read-only questions and drafts produce zero training starts or discovery-state mutations.
- Repeated submissions, process restarts and duplicate external events produce no duplicate work.
- All compute is charged to the correct discovery or verification budget; unknown monetary costs remain unknown.
- Verification displays incomplete results and measured variability without overstating confidence.
- Retrieval and follow-up context preserve project/protocol boundaries and sealed-test restrictions.
- Report numbers reconcile with frozen records, and publishing/model promotion remain distinct actions.
- Existing catalog, project, research, replay, Launch and final-evaluation tests continue to pass.

## Reference

W&B, [Create a report](https://docs.wandb.ai/models/reports/create-a-report), checked 2026-09-13: programmatic Reports API is in Public Preview; saving uploads the report. This supports the separate local-review/publish boundary. ARIA transport behavior is grounded in the repository's `AUTOMATION.md`, `aria_client.py` and `launch_step.py`; live availability must be reverified in Session 1.
