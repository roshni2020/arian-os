# Session 2: Ask about selected runs

Implemented 2026-09-13 in one coordinated implementation run, using a lead and three specialists with disjoint ownership. This is a development milestone, not a paid training session.

## Delivered

Compare selection passes exact experiment identities. Saved answers retain original evidence; readable citations expand exact source values. Request history survives navigation and API restart.

## Files

Paths are relative to repository root (assistant paths are under wildfire_researcher/): frontend/src/components/research/AssistantWorkspace.tsx; frontend/src/lib/assistant.ts; ResearchAnalysis.tsx.

## Validation

Live answer compared exp-000 and exp-001, exact validation AP, false positives, differing thresholds; confirmed in browser.

Shared schema/API: assistant v1, /api/assistant. Persistent stores: assistant.sqlite3 beside research DB; reviewed draft linkage table in research DB.

## Resumption

Read IMPLEMENTATION.md and verify live processes before any restart. Preserve original research data. Existing immutable Launch source captures must be recaptured through the normal workflow before dispatching changed code. No credentials are stored in this handoff.
