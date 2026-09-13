# ARIA integration through W&B Automations

There is no public prompt-to-ARIA API and the `wandb` SDK cannot create ARIA automations (verified: `Api.automations()` does not even list them). The proven path is:

```
worker: experiment run finishes ──(W&B Automation: run status = finished, name regex)──▶ ARIA (new conversation)
          ▲                                                                                  │
          │ waits for artifact                                                               │ reads <session>-state:latest
          │                                                                                  ▼
       <session>-proposal-r<N>  /  <session>-decision-final   ◀── ARIA logs artifact via wandb SDK
```

Each event starts a **new** ARIA conversation, so the worker publishes the complete research state (history, error breakdowns, feature importance, capability manifest, budget, instructions, rejection feedback) as artifact `<session>-state` on every cycle, *inside* the experiment run, before the run finishes. The state carries `state_revision`; ARIA must echo it and name its artifact `<session>-proposal-r<revision>`, so stale or duplicated responses are rejected (`experiments.validate_proposal`).

## Automations that exist in project `ali-amjad52114-r42/wildfire-autonomous-researcher`

| Name | Run-name filter | Purpose |
|---|---|---|
| `ARIA wildfire researcher - all sessions` | `^wf-\d{8}-\d{6}-[0-9a-f]{4}-(exp-\d+|control-r\d+)$` | generic; serves every session started from the UI or CLI (auto-generated ids). ARIA derives the session id from `${run_name}`. |
| `ARIA wildfire researcher - wf-20260913-live1` | `^wf-20260913-live1-(exp-\d+|control-r\d+)$` | the first verified live session (budget 3). |

Both: event **Run status change → Finished**, action **Trigger ARIA**, scope project. ARIA's own upload runs are named `<session>-aria-upload-r<N>` and the final-evaluation run `<session>-final-evaluation`, so they never match the filters (no recursive invocation).

## Reproducing the automation without chat history

1. Start the backend and get the prompt: `GET /api/automation-prompt/<any-session-id>` or `python -m wildfire_researcher.cli automation-prompt --session <id>` (add `?generic=false` / read the CLI header for a session-specific variant).
2. W&B → project → Automations → Create automation:
   - Event: *Run status change*, states: **Finished** only, *Filter on run name* = regex above.
   - Action: *Trigger ARIA*, paste the prompt (it is ~2,070 characters; the limit is 4,000 after template substitution).
   - Name it, create.
3. Start a session. The baseline run's finish event triggers the first ARIA conversation automatically; no manual bootstrap.

The generic prompt (from `aria_client.automation_prompt(None, entity, project)`):

```
You are the autonomous researcher for W&B project ${project_name}. Run ${run_name} just finished.
SESSION = ${run_name} with its trailing '-exp-<digits>' or '-control-r<digits>' suffix removed (...). Replace <SESSION> below with it.
Goal: raise validation AUPRC for WildfireIA initial-attack failure (published test benchmark 0.533; validation scores are not test scores).
Steps:
1. Using the wandb SDK, download artifact `<entity>/<project>/<SESSION>-state:latest` (type research-state) and read state.json. Trust only that state.
2. Study objective, protocol, capabilities, history (...), failed_experiments, rejected_messages_at_this_revision and instructions.
3. If instructions ask for a final decision: write decision.json (...) and log it as artifact `<SESSION>-decision-final`. Stop.
4. Otherwise decide KEEP/REJECT for awaiting_decision_for_experiment_id (...), then design ONE next experiment (...). Only use models, feature_protocols, weather_days and bounded hyperparameters listed in capabilities. Never repeat a configuration in history. Do not try to use test data.
5. Write proposal.json exactly following capabilities.response_contract.proposal (...) and log it as artifact `<SESSION>-proposal-r<state_revision>` (...).
Respond only through those artifacts. Do not run training yourself.
```

## Contract enforced by the worker

- Proposal: closed schema (`schema_version, session_id, state_revision, proposal_id, observation, hypothesis, expected_result, reason, experiment, previous_decision`), no extra keys, bounded typed hyperparameters, official feature protocols only, no duplicate canonical configuration, `previous_decision.experiment_id` must be the last completed experiment. ARIA output is data: nothing in it is executed, interpolated into a shell, or used as a path.
- Invalid proposals get structured feedback: the worker records the rejection, bumps the state revision, publishes the new state through a control run `<session>-control-r<N>` (which re-triggers ARIA), and waits for a corrected proposal. After `ARIA_MAX_REJECTIONS` (3) consecutive rejections the session stops with status `error`; the worker never picks an experiment itself.
- Timeouts: `ARIA_WAIT_SECONDS` (default 1800) per cycle. On timeout the session goes to `error` with the reason and is resumable (`resume`) once ARIA responds; no fallback experiment is executed.
- Idempotency and recovery: experiments are claimed transactionally in SQLite (unique `(session_id, config_key)` and `(session_id, iteration)`); a restart re-runs an interrupted claim instead of creating a duplicate; duplicate proposal ids and stale revisions are rejected.

## Provenance recorded per exchange

`aria_messages` table: direction, kind, artifact reference and version, artifact digest, file SHA-256, state revision, accepted flag and structured feedback. ARIA's conversation id is not exposed through the artifact API; automation history in the W&B UI (Automations → History) links each dispatch to its conversation.

## Limits stated honestly

- Weave traces `receive_aria_output`, `validate_experiment`, `execute_training`, `evaluate_result`, `record_aria_decision`, `publish_research_state` (what happens locally). The training/evaluation/publish calls carry the experiment's `wb_run_id`; receive/validate/decision calls happen between runs and are project-level calls. ARIA's internal analysis steps run in W&B's environment and are **not** traced here; no spans are fabricated for them. ARIA's stated observation, hypothesis, reason, decision and learning are stored verbatim as received outputs.
- Rate limit: 3 ARIA conversations per minute per automation. The worker's cadence (one event per experiment) is far below that.
- Only the automation creator can edit it. To disable an automation without losing history, change its regex to a non-matching one (e.g. `a^`).
