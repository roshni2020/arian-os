# Session 3: Error groups to reviewed experiments

Implemented 2026-09-13 in one coordinated implementation run, using a lead and three specialists with disjoint ownership. This is a development milestone, not a paid training session.

## Delivered

Group selection opens a scoped proposal. A verified response becomes a frozen review draft; explicit Start creates a fresh connected local study. First proposal must match the reviewed configuration.

## Files

Paths are relative to repository root (assistant paths are under wildfire_researcher/): assistant/drafts.py; experiments.py; state.py; ErrorAnalysis.tsx.

## Validation

Real error_proposal aria-assistant-7382cee815a0425fba4236a07284ad70 succeeded with actual by_state/CA evidence; earlier acceptance request with unknown dimension state was retained as rejected. Draft tests cover manual-origin rejection, stale versions, concurrent idempotency and configuration enforcement.

Shared schema/API: assistant v1, /api/assistant. Persistent stores: assistant.sqlite3 beside research DB; reviewed draft linkage table in research DB.

## Resumption

Read IMPLEMENTATION.md and verify live processes before any restart. Preserve original research data. Existing immutable Launch source captures must be recaptured through the normal workflow before dispatching changed code. No credentials are stored in this handoff.
