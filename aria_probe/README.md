# ARIA integration probe

This is an isolated synthetic-data integration test, **not WildfireIA**. Every score
is a validation score on synthetic data and is never compared to 0.533.

The local worker runs a fixed baseline, publishes state to W&B Artifacts, and waits
for proposals written by real ARIA. It has no fallback researcher. It trains at
most two additional experiments and waits for a final ARIA decision.

## Run

From the workspace root, install `aria_probe/requirements.txt` into `.venv`.
Set `WANDB_API_KEY` through the environment (on Windows the worker can read the
existing per-user environment variable). Never place a key in a config file.

```powershell
.\.venv\Scripts\python.exe aria_probe/probe.py baseline
.\.venv\Scripts\python.exe aria_probe/probe.py watch --wait-seconds 600
.\.venv\Scripts\python.exe -m unittest discover -s aria_probe -v
.\.venv\Scripts\python.exe aria_probe/verify.py
```

The default project is `ali-amjad52114-r42/aria-integration-probe`.
The default session is `aria-probe-20260913`; use `--session` for a new test.
Local results live under the ignored `artifacts/<session>/` directory.

## ARIA artifact contract

ARIA should read `<session>-state:latest` (type `research-state`, file `state.json`).
For iteration 1 or 2 it must publish `<session>-proposal-<iteration>` (type
`research-proposal`, alias `latest`, file `proposal.json`) containing:

```json
{
  "observation": "Evidence from the actual state",
  "hypothesis": "One proposed improvement",
  "reason": "Why this experiment follows from the evidence",
  "experiment": {
    "model": "logistic_regression",
    "feature_count": 4,
    "C": 1.0,
    "class_weight": null
  },
  "previous_decision": {
    "decision": "KEEP",
    "reason": "Assessment of the preceding experiment",
    "learning": "What the preceding result taught us"
  }
}
```

The example is a schema illustration, not a preselected ARIA experiment. ARIA must
choose the actual values. Allowed feature counts: 2, 4, 8, 12; C: 0.01 to 10;
class_weight: null or balanced. No code, commands, URLs, arbitrary paths, other
models, or extra configuration keys are accepted by the validator.

After two ARIA-selected experiments, publish `<session>-decision-final` (type
`research-decision`, alias `latest`, file `decision.json`) with decision, reason,
and learning. No third training experiment will be executed.

## Provenance and limits

Weave traces the received proposal, validation, and actual training. It does not
fabricate ARIA's internal reasoning stages. Preserve the ARIA conversation as
authorship evidence: an artifact labeled ARIA alone is not cryptographic proof
of authorship. The best numeric score is computed from measured results even if
ARIA decides to retain a weaker experiment as useful research evidence.

This prototype uses one worker; do not start multiple watchers for one session.
It is a protocol probe, not production queueing. The completed test demonstrated
automatic event-triggered continuation after a browser bootstrap: W&B Automation
invoked ARIA, which published the second proposal and subsequently the final
decision. See [RESULTS.md](RESULTS.md) for evidence and remaining limitations.
The temporary automation's trigger was neutralized after testing with a regex
that matches no run name (`a^`); its execution history is preserved. A fresh session requires a
correspondingly scoped ARIA automation and an initial ARIA proposal; the worker
does not invoke an undocumented ARIA endpoint.
