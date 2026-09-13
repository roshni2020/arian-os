# Session 1: Request and evidence foundation

Implemented 2026-09-13 in one coordinated implementation run, using a lead and three specialists with disjoint ownership. This is a development milestone, not a paid training session.

## Delivered

Closed v1 envelopes, immutable evidence, durable outbox, cancellation, bounded retries, restart reconciliation, and verified W&B Automation. Existing research triggers remain separate.

## Files

Paths are relative to repository root (assistant paths are under wildfire_researcher/): assistant/contracts.py, evidence.py, storage.py, requests.py, transport.py; scripts/assistant_worker.py.

## Validation

Real ask request aria-assistant-88997dac92764c3d802a965f51428c88 completed; output:v0 digest 283492e55e42f55c5695dabfd121d4c8. Schema/citation and transport tests pass.

Shared schema/API: assistant v1, /api/assistant. Persistent stores: assistant.sqlite3 beside research DB; reviewed draft linkage table in research DB.

## Resumption

Read IMPLEMENTATION.md and verify live processes before any restart. Preserve original research data. Existing immutable Launch source captures must be recaptured through the normal workflow before dispatching changed code. No credentials are stored in this handoff.
