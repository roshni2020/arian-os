# Session 4: Study planning

Implemented 2026-09-13 in one coordinated implementation run, using a lead and three specialists with disjoint ownership. This is a development milestone, not a paid training session.

## Delivered

Plans declare experiment budget, initial sequence, success criteria and stopping conditions. Fixed baseline remains additional to budget. Supported project hash is rechecked before local execution.

## Files

Paths are relative to repository root (assistant paths are under wildfire_researcher/): assistant/drafts.py; frontend/src/components/benchmarks/ProjectOverview.tsx.

## Validation

Real study_plan aria-assistant-ae99320677104e11965851097b1b6c27 succeeded. Tests verify project binding and exactly one fresh session under repeated/concurrent Start.

Shared schema/API: assistant v1, /api/assistant. Persistent stores: assistant.sqlite3 beside research DB; reviewed draft linkage table in research DB.

## Resumption

Read IMPLEMENTATION.md and verify live processes before any restart. Preserve original research data. Existing immutable Launch source captures must be recaptured through the normal workflow before dispatching changed code. No credentials are stored in this handoff.
