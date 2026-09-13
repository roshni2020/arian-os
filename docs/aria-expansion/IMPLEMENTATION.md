# ARIA research workflows — implementation and acceptance

Implemented 2026-09-13 after explicit user authorization. All eight development milestones were completed in one coordinated run with a lead and three specialist agents. No separate user-owned tasks were created.

## Delivered user flow

1. **Projects → Plan with ARIA:** review the proposed objective, experiment sequence, success criteria, stopping conditions and budget. An executable plan creates a separate connected local research session only after Start reviewed study. The fixed baseline is additional to the proposed-experiment budget. An unlinked project is linked to its started study; follow-ups to linked studies preserve the old link.
2. **Research journal → Compare → Ask ARIA about these runs:** submit a scoped asynchronous question, leave and return, inspect the saved answer and expand exact evidence citations.
3. **Error analysis → Dimension → group → Investigate with ARIA:** review a concrete supported experiment and its hypothesis/tradeoffs. Unknown dimensions or groups fail explicitly. Subgroup measurements cannot be replaced by overall metrics. No training starts when a proposal or draft is created.
4. **Verify improvement:** freeze two configurations and 2–10 paired seeds (4–20 child runs). Start explicitly; inspect every child, paired AP differences, mean, sample SD, min/max and incomplete results. Cancel or resume interrupted work without rerunning completed children. A selected ablation configuration can be compared with a baseline; arbitrary multi-arm sweep generation is outside this release.
5. **Related findings:** retrieve compatible prior successes and failures, source links, dates and verification references. Exclude findings from new requests. New requests refresh eligible findings and freeze up to eight into their evidence snapshot. Fallback/replay and test-exposed sources are ineligible. Missing, changed and stale sources are skipped.
6. **Research report → Report & export:** review the real ARIA narrative with frozen deterministic tables, configurations, recorded decisions, verification, limitations and cited evidence appendix. Export Markdown/JSON locally. Publishing to W&B is a separate explicit action, with remote readback and ambiguous-publication reconciliation. Imported narratives are labeled unverified. No automatic model promotion or official-test evaluation.

Later live execution supersedes the earlier unstarted-verification snapshot below: see [END_TO_END.md](END_TO_END.md) for the completed reviewed study, four actual verification jobs, and final local exports. The historical acceptance results below retain their original scope.

## Validation

Final broad backend command:

```powershell
.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_loop_offline.py --ignore=tests/test_runner.py --ignore=tests/test_official_parity.py -k 'not test_start_fallback_session_runs_and_persists' --disable-warnings
```

Result: **457 passed, 1 deselected**, 11 deprecation warnings. The excluded files exercise canonical model fitting/official parity; they were not all rerun during this change. Separately, the real offline cancel/resume regression passed after one earlier failure during concurrent load; the failure was not reproduced, and its assertion now includes the recorded error for future diagnostics. No production loop behavior was changed to hide it.

Frontend: **51 tests passed**, full ESLint passed, and the isolated production build (including TypeScript and route prerendering) passed using `NEXT_DIST_DIR=.next-benchmarks`. The dev build was preserved. Tests cover strict seeds, safe report rendering, immutable drafts, stale versions, project/protocol binding, cancellation, request recovery, idempotency, evidence grounding, retrieval exclusions and mocked publication.

Browser checks on the running application covered Compare selection, saved real answers, citation labels, project planning before execution, reviewed study draft, actual California error-row context, paired-seed verification review, real cross-session findings and readable report export. The narrow browser viewport showed wrapped controls and scrollable report/table content.

## Real ARIA acceptance

A dedicated W&B Automation named **ARIA research assistant — analysis requests** watches finished runs in `ali-amjad52114-r42/wildfire-autonomous-researcher` matching `^aria-assistant-[a-f0-9]{32}$`. Response run names end in `-response`, so they do not recursively trigger the automation. Existing research Automations are unchanged.

Four actual ARIA responses passed validation:

| Kind | Request ID |
| --- | --- |
| Ask | aria-assistant-88997dac92764c3d802a965f51428c88 |
| California proposal | aria-assistant-7382cee815a0425fba4236a07284ad70 |
| Study plan | aria-assistant-ae99320677104e11965851097b1b6c27 |
| Report | aria-assistant-9606ca0331764bf5b20abac1b87e3a89 |

Versioned artifact references and digests are in `live-acceptance.json`. The corrected California proposal cites 14 candidate misses versus 18 baseline misses among 22 positives, separately from overall validation metrics. It also uses a prior failed configuration as evidence for a new falsifiable proposal.

The first subgroup probe used an unknown dimension (`state` instead of `by_state`). It was retained as rejected, and request creation now rejects such scope errors. The corrected artifact briefly hit an overly broad citation check for a truthful statement that a prior run lacked subgroup cells. That check was narrowed and tested; the same authentic artifact was revalidated, without another ARIA call or changed content.

`acceptance-report.md` and `.json` are actual template-v2 local exports. They include an unstarted verification plan, clearly marked incomplete. W&B publication and verification execution were tested with controlled adapters/executors, not by publishing a real report or launching new full-data verification. Monetary ARIA cost was not returned by this transport and is not estimated here.

## Persistence and operation

- Main API: `http://127.0.0.1:8000`; frontend: `http://localhost:3000`.
- Assistant v1 routes: `/api/assistant`.
- `assistant.sqlite3` beside the research database stores requests, outbox, transport proof, verification, findings and report snapshots.
- The main research DB gains the additive `assistant_reviewed_drafts` table so draft-to-session linkage can commit atomically. Original research tables/results are preserved.
- API startup launches one assistant recovery loop. GETs do not dispatch ARIA, start training or publish. Request runs use W&B `reinit="create_new"` to avoid reusing a training run.
- A saved proof enables the matching transport identity only after a validated real artifact response. Unknown capability stays disabled in the UI.
- Queued/waiting work resumes after process restart. Cancellation stays final. Invalid responses display a rejection reason and require a fresh request; ambiguous dispatches require operator reconciliation. Timeouts retain the original dispatch deadline.

Operator commands:

```powershell
.venv/Scripts/python.exe scripts/assistant_worker.py setup
.venv/Scripts/python.exe scripts/assistant_worker.py pending
.venv/Scripts/python.exe scripts/assistant_worker.py reconcile REQUEST_ID
.venv/Scripts/python.exe scripts/assistant_worker.py poll REQUEST_ID
.venv/Scripts/python.exe scripts/assistant_worker.py import REQUEST_ID response.json
```

Manual imports remain review-only and never establish transport proof. Do not run a second recovery worker alongside the API unless intentionally operating a separate database; the API already performs recovery.

## Runtime and rollback

The existing 15-experiment study `wf-20260913-174109-6335` completed before the backend was reloaded. No active training was interrupted. The temporary API on port 8002 was stopped; port 8001 was not touched. The frontend remains on port 3000. Backend logs are under `tmp/assistant-api.*.log`.

Before any later restart, inspect current worker state; saved PIDs are not durable identities. To roll back this feature, stop only an idle API, revert assistant route/UI integration, and preserve both databases and W&B artifacts. Do not delete research history. Existing immutable Launch source captures must be recaptured through the normal workflow before dispatching changed code.

The original README edits and slide deck present before implementation were left intact. See session-1 through session-8 handoffs for ownership and milestone boundaries.
