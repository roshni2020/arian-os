# ARIA research operations

The W&B Automation/artifact loop is the supported execution path. A second path, in which ARIA submitted each validated step to **W&B Launch**, ran one complete session; that session is preserved below as a record, and the Launch bridge code and the local alert monitor have been removed from the repository (they remain in git history).

## Published research knowledge

ARIA independently examined a fixed snapshot of 49 runs: 21 measured experiments, 17 proposals, three completed research sessions, and one cancelled baseline-only setup attempt. The report identifies 13 distinct configurations, incumbent-relative deltas, failures to improve, and decision consistency. New operations and Launch runs are outside that historical snapshot.

- [ARIA research report](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher/reports/Wildfire-Autonomous-Researcher-Retrospective-—-2026-09-13--VmlldzoxNzkyNDE5Ng==)
- [Focused saved workspace](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher?nw=yhc341igcw4)
- [Separate controller/operations workspace](https://wandb.ai/ali-amjad52114-r42/wildfire-autonomous-researcher?nw=r4e1aykiznb)
- Corrected machine-readable artifact: `ali-amjad52114-r42/wildfire-autonomous-researcher/aria-operator-retrospective:v1`
- Local copy: `artifacts/operations/aria-retrospective-v1/`

The report was independently checked against all 21 local experiment scores. Two initial ARIA interpretation errors were corrected by ARIA in the same report: all 126 historical Weave calls have an end timestamp; 77 have W&B run links that support session attribution. The cancelled setup session's last cloud state is stale. No token usage/internal ARIA traces are available in those 126 calls. Missing fields in a projected response do not prove missing persisted telemetry.

## Preserved model and dataset lineage

`scripts/preserve_winner.py` reconstructed session `wf-20260913-104003-2c71` experiment `exp-011` using its recorded configuration and research seed. Every validation probability exactly matched the historical prediction file. The serialized model was reloaded and checked again.

- Model: `ali-amjad52114-r42/wildfire-autonomous-researcher/wildfireia-validation-winner:v0`
- Dataset: `wildfireia-pinned-dataset:v0` is explicitly a **reference manifest**, containing pinned upstream revision/file hashes and feature definitions. It does not claim to contain the raw dataset.
- Registry: `ali-amjad52114-r42-org/wandb-registry-Wildfire Research Models/WildfireIA validation winner:validation-winner`
- Aliases: `validation-winner`, `reconstructed`. No production/certified-test alias.
- Registry access is organization-scoped; restricted registries were rejected by the account's plan.
- Evidence: `artifacts/operations/preserved-winner/publication.json`.

The reconstruction has **no new test evaluation**. The historical five-seed final model files did not exist and were not retrospectively fabricated. New ordinary experiments now save model bundles with feature order, fitted preprocessing statistics, native XGBoost or joblib serialization, and a checksum. The input contract is canonical discovery-time feature columns, not arbitrary incident JSON. Only load trusted project-owned joblib files.

## Recorded W&B Launch session

The session ran on local compute through the official `local-process` Launch agent, not CoreWeave. The console still shows it read-only; Launch sessions cannot be resumed by the local worker.

Session `launch-20260913-133047-0467` completed with real ARIA using immutable job `wildfire-validated-local-step:v2`:

| Step | Measured run | Validation AUPRC | ARIA decision |
| --- | --- | --- | --- |
| Fixed metadata logistic baseline | `jc39ek40` | 0.1841706764 | REJECT |
| Full-feature default XGBoost | `48upfkuz` | 0.4829886184 | KEEP |
| Same XGBoost, scale_pos_weight 1.5 | `balfld3v` | 0.4999662448 | KEEP; final recommendation |

The first proposal changed both model and feature protocol; the second isolated one parameter.
This new winner uses default depth 4, unlike the preserved historical depth-3 winner.
ARIA's controller runs are `sfgw1glz`, `9aaytrms`, and `ban896uu`. All three carry native
`_wb_agent` thread/turn provenance. Use actual run records and session/config matches
when reconciling the submitted jobs and their measurements.
The later job `v3` captures the API resume guard; the successful live trajectory used `v2`.

Independent checks matched every submitted proposal (including the validator's empty
hyperparameter default), real metric, model artifact, final decision and linked Weave span.
The final state is `launch-20260913-133047-0467-state:v3`; no official test evaluation ran.
Replay: `artifacts/launch-20260913-133047-0467/replay.json`.
Cloud replay and independent verification:
`ali-amjad52114-r42/wildfire-autonomous-researcher/launch-20260913-133047-0467-verified-replay:v0`.
Local verification: `artifacts/operations/launch/verified.json`.
ARIA's own independently reconciled trajectory:
`ali-amjad52114-r42/wildfire-autonomous-researcher/aria-launch-operator-evidence:v0`
(digest `eb6af01856fe9312fffe9973ed2a9e11`), downloaded under
`artifacts/operations/aria-launch-evidence/`. Its `replay.json` is a Launch payload
timeline; use the application's verified replay above for the console's Import Replay.

The first baseline attempt failed before training because Windows W&B cannot lock its run files in a WSL UNC working directory. Setting the child working directory to the native project path fixes this. The failed job is retained as operational evidence; its identical unmeasured baseline configuration was retried.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The final Python suite passed **80 tests** (three upstream warnings, 188.01 seconds).
Frontend: **3 tests**, TypeScript, ESLint and production build passed. The console's live
Launch session was checked in Chrome. Both HTTP services returned healthy responses after
the backend restart. The corrected Launch entrypoint is additionally verified by the
completed live cycle. Historical test scores remain descriptive above-reference results
because the published seeds are unknown and later research followed earlier test disclosure.
No new test evaluation was performed to verify these integrations.
