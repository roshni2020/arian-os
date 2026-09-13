# Build the ARIA Wildfire Researcher — implementation handoff

You are taking over an existing project. Build and test the complete working
vertical slice, not just a plan or scaffold. Inspect the existing work first and
preserve its evidence. The user authorizes writing code and running bounded tests.
Use reasonable implementation judgment; ask only for concrete missing access or
decisions that materially block work. Do not provision paid infrastructure without
a known budget. No organizer is currently available to answer integration questions.

## 1. Goal and precedence

Build a hackathon project for the CoreWeave / Weights & Biases Agent Loops
Hackathon: real ARIA autonomously researches wildfire initial-attack failure,
trying to beat the published WildfireIA result of 0.533 AUPRC while respecting
the official evaluation protocol.

The product is the observable research loop:

OBSERVE → HYPOTHESIZE → DESIGN ONE EXPERIMENT → VALIDATE → TRAIN → EVALUATE
→ ARIA KEEP/REJECT → NEXT QUESTION.

ARIA must choose hypotheses, feature/model changes, experiment configurations,
retention decisions, and next directions. Do not replace it with your own LLM,
heuristics, Optuna, grid search, or a scripted trajectory wrapped in explanations.
An honest failure to beat the benchmark is an acceptable research outcome.

These instructions incorporate later corrections and override conflicting parts
of the original brief. In particular: ARIA is mandatory for the real demo; no
silent fallback; validation is not an official test score; the already successful
synthetic probe is not a wildfire result.

Read the original full product brief here for additional UI and deliverable details:
`C:\Users\aliam\.codex\attachments\49d76479-5f3e-41ea-81a5-9abb668307ac\pasted-text.txt`.
If working elsewhere, ask the user for this attachment only if unavailable; this
handoff is sufficient to start.

## 2. Workspace and what already exists

Workspace: `C:\AI\Projects\focus`, Windows PowerShell.

Read these before changing anything:

- `aria_probe/probe.py`: working local constrained worker and artifact protocol.
- `aria_probe/test_probe.py`: four passing validator tests.
- `aria_probe/verify.py`: read-only checks of remote runs, metrics, and Weave calls.
- `aria_probe/README.md` and `aria_probe/RESULTS.md`: instructions and live evidence.
- `artifacts/aria-probe-20260913/state.json`: actual completed synthetic research state.
- Other files under that ignored artifact directory: downloaded ARIA proposals,
  final decision, and predictions. Final decision downloaded under `proposal-3`.

Python 3.12 virtual environment `.venv` exists. Installed versions include
wandb 0.30.0, weave 0.53.9, scikit-learn 1.9.1. Requirements are pinned in
`aria_probe/requirements.txt`. Inspect current dependencies before installing.
Check for applicable AGENTS.md and existing user changes.

Useful commands from the workspace root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s aria_probe -v
.\.venv\Scripts\python.exe aria_probe/verify.py
```

The W&B credential exists as Windows per-user environment variable
`WANDB_API_KEY`; a new process may not inherit it. The existing `credential()`
helper reads it using winreg. Reuse that approach if needed. Never print, commit,
hardcode, put in frontend code, or include keys in run metadata. Do not ask the
user to paste credentials into chat. A TypeSafe AI key was mentioned earlier but
its service capabilities and integration were not verified; do not assume it is
required or usable. Do not add it just because it was mentioned.

The full app, WildfireIA integration, data preparation, and frontend are NOT built.
The probe is evidence and a starting pattern, not a production queue.

## 3. What was actually verified with real ARIA

W&B entity: `ali-amjad52114-r42`.
Probe project: `aria-integration-probe`.
Session: `aria-probe-20260913`.

| Trial | Configuration | Synthetic validation AUPRC | ARIA decision |
|---|---|---:|---|
| Baseline | Logistic regression, 2 features, C=1, no weighting | 0.3573556168800534 | REJECT as incumbent |
| 1 | ARIA chose 4 informative features | 0.5396946887587629 | KEEP |
| 2 | ARIA chose balanced class weighting | 0.5266460741237637 | REJECT as incumbent |

These are generated classification data, not wildfire data. They cannot support
a benchmark claim even though one number exceeds 0.533.

Real integration sequence:

1. A browser conversation with ARIA produced proposal 1 as a W&B artifact.
2. A local worker read it, validated it, trained, and published new state.
3. A W&B Automation was created after that first experiment. One control run,
   `aria-probe-20260913-wake-1`, triggered it without logging fake training metrics.
4. Automation invoked ARIA. ARIA read the state, kept trial 1, and wrote proposal 2.
5. The worker ran trial 2. Its finish event automatically invoked ARIA again.
6. ARIA wrote the final REJECT decision. The worker persisted status `complete`.

Both choices came from real ARIA. Trial 2 and final review required no manual
follow-up. The bootstrap was manual: do not call the entire test hands-free.
All three training runs finished; eight Weave traces succeeded; four unit tests
passed. The worker process has exited.

Evidence:

- Project: https://wandb.ai/ali-amjad52114-r42/aria-integration-probe
- Baseline run: `6vtgcf2c`; trial 1: `t581viv8`; trial 2: `bmg5dqp3`.
- Final decision receipt run: `5l4alegq`.
- Traces: https://wandb.ai/ali-amjad52114-r42/aria-integration-probe/weave/traces
- Original ARIA conversation: `01a09a1d-3e87-7c82-b8d5-5b321200cb76`.
- Automatic proposal-2 conversation: `01a09a22-3acd-7e70-a237-97775d913325`.
- Artifacts: `aria-probe-20260913-proposal-1:v0`,
  `aria-probe-20260913-proposal-2:v0`, `aria-probe-20260913-decision-final:v0`.

Temporary automation name: `ARIA integration probe — two experiments`.
Its trigger was neutralized after completion using nonmatching regex `a^`.
There was no visible disable switch. Its history is preserved. Do not assume it
is running or reuse its fixed session contract for the full project.

## 4. ARIA integration architecture: use the proven path

The previous agent found no invoke-ARIA tool among 30 W&B MCP tools. Do not infer
direct ARIA access just because W&B MCP works. Public direct arbitrary-prompt
ARIA API access was not established. The verified path is W&B Automations,
configured through the UI, invoking ARIA on project events. ARIA can use a shell
and W&B SDK in its own environment to read/write artifacts.

Check current official documentation before relying on new capabilities:

- https://docs.wandb.ai/models/automations
- https://docs.wandb.ai/models/automations/create-automations/aria
- https://docs.wandb.ai/models/automations/api

The previous test found the Python automation SDK did not support ARIA actions;
UI creation worked. Do not invent API mutations or undocumented endpoints.
Browser authentication and API authentication are separate. The user signed into
W&B in Codex's browser, but Claude may not inherit that browser session.

Implement `ARIAClient` as an adapter around asynchronous state/proposal/decision
exchange. W&B Artifacts hold versioned research state and structured outputs.
The backend performs validation, execution, persistence, and presentation only.

For a new session, configure the automation BEFORE publishing the baseline's
completion/control event so bootstrap can also be automatic. Include the session
and state reference in the triggering run's configuration; tell ARIA to inspect
that run. Verify supported automation template keys, rather than assuming custom
keys are expanded. Filter triggers to intentional control events or training runs;
ARIA's own artifact-upload runs must not trigger recursive invocations.

Each event creates a NEW ARIA conversation. Therefore send the complete relevant
research state on every cycle. A 202 response/thread_id means dispatched, not
finished: wait for a validated result artifact. Record conversation provenance
where available, exact artifact version/digest, state revision, and triggering run.

Use unique session/revision/iteration IDs, proposal IDs, explicit schema versions,
bounded waits, retry limits, stale-response rejection, cancellation, durable
processing status, and idempotency. Validate state revision before accepting a
proposal. Duplicate events must not cause duplicate training. Single-worker locks
or transactional claims are sufficient initially. Persist before event publication
and recover interrupted runs without silently repeating completed work.

Invalid proposals should produce structured rejection feedback for ARIA with a
bounded retry budget; do not quietly choose the next experiment yourself.
Treat ARIA output as data, never execute arbitrary generated code or shell commands.

Expose `ARIA_MODE=connected` only when the actual integration is available, and
distinct waiting/error states when appropriate. An optional local fallback can
exist for DEVELOPMENT TESTS ONLY with explicit `ARIA_MODE=fallback` labeling.
Never use it as the judged ARIA researcher or silently switch to it on timeout.

## 5. Sponsor-first tool policy

Prefer the smallest stack:

- ARIA: autonomous researcher.
- W&B Models: experiment tracking, configs, metrics, artifacts.
- Weave: observable research exchange and execution traces.
- W&B Automations: event-driven ARIA invocation.
- CoreWeave: intended hosted compute when access/budget is available.
- W&B Launch: optional job submission if it simplifies CoreWeave execution.
- Python, scikit-learn, XGBoost: ML implementation.
- FastAPI + SQLite: small local backend and durable state.
- Next.js + TypeScript + Tailwind: frontend; use minimal UI/chart dependencies.

Open-source libraries are fine. Avoid extra paid platforms, external databases,
third-party agent frameworks, or another LLM service unless a concrete requirement
cannot be met by sponsors. Explain the gap before adding such a service.

No Launch queue/active agent was found in the team. Docker CLI existed but the
daemon was unavailable; a Docker Desktop start attempt hung and was stopped.
No Kubernetes context/CoreWeave credentials were established. Reinspect current
environment; don't claim CoreWeave execution based on the local probe. Keep a
local training executor so P0 can work, and make hosted execution an adapter.

## 6. Scientific protocol — critical corrections to the original demo brief

Official source: https://github.com/LabRAI/WildfireIA
Dataset specified in brief: `WildfireIA/Anonymous-WildfireIA` on Hugging Face.
Read official code, data instructions, evaluation scripts, and paper. Pin the
repository commit and record dataset/cache provenance. Do not invent a split.

Earlier inspection reported 2016–2018 training, 2019 validation, and 2020 test;
the published 0.533 is a test result averaged over five seeds, with AUPRC computed
using `average_precision_score`. It also found discovery-day D timing semantics,
not necessarily an instantaneous timestamp cutoff. These are handoff findings to
VERIFY against the pinned official implementation before coding claims.

Write a short `BENCHMARK_PROTOCOL.md` resolving task/label, cohort, years/split,
feature eligibility and timing, preprocessing, seed list, aggregation, and exact
metric computation. Use official evaluation code where possible.

ARIA iterates on TRAIN/VALIDATION only. Do not send test results/errors to ARIA
to drive feature or hyperparameter choices. Select/freeze the final configuration
before official held-out testing. Do not repeatedly test candidates until a score
crosses the target. Follow official training/refit and multi-seed evaluation steps.

Separate scores and UI claims:

- Synthetic/subsample runs: DEV SCORE, never benchmark comparable.
- Validation experiments: VALIDATION AUPRC, useful for selection but not evidence
  of beating the published test benchmark.
- Official final evaluation: exact comparable test metric with seed aggregation
  and provenance, eligible for a benchmark claim only if strictly greater than 0.533.

Do not subtract a validation score from the published test score and present that
as a scientific improvement. A target reference line is allowed only with clear
split labels. The backend, not frontend arithmetic or ARIA text, gates the
`PUBLISHED BENCHMARK BEATEN` status.

Exclude forbidden predictors such as final size, containment timestamps, and
post-discovery information under the official protocol. Fit preprocessing on
training only. Do not expose leakage columns through error-analysis suggestions.
The original brief's fire-size bucket analysis must not become a model input or
test-feedback channel; prefer analyses using eligible predictors initially.

Detect existing data/caches before downloading or rebuilding. Start tabular only.
Use official supported feature protocols; do not invent convenient combinations
without verifying their implementation and comparability. Record cache keys for
repository revision, dataset, representation, weather window, and feature protocol.

## 7. Research state and experiment contract

Baseline: metadata-only logistic regression, with a real measured score. Do not
force a 30–40% result or weaken it artificially to fit the story.

Initial models: logistic regression and XGBoost. Add Random Forest/LightGBM only
if useful and easy. Defer spatial/temporal neural models and ensembles until P0.

Give ARIA a capability manifest of supported feature groups, model families,
bounded hyperparameters, weather windows, compute costs, and validation rules.
Require one meaningful change per experiment where possible; ARIA should explain
multi-variable changes. Default configurable budget: 15 experiments, explicitly
define whether baseline/final seeds count. Set runtime/memory/CPU limits too.

Research state includes target 0.533, score type/split, numeric best, current score,
full experiment history, tested features/models/hyperparameters, rejected/failed
experiments, false-negative/false-positive summaries, feature importance, PR
information, runtime/resources, and remaining budget. Include per-group sample
counts so ARIA does not make strong claims from tiny groups.

Required proposal content, with a strict typed schema adapted to official names:

```json
{
  "schema_version": 1,
  "session_id": "...",
  "state_revision": 3,
  "proposal_id": "...",
  "observation": "Evidence from measured results",
  "hypothesis": "A falsifiable expected improvement",
  "experiment": {
    "model": "logistic_regression",
    "feature_protocol": "a_verified_supported_protocol",
    "weather_days": 5,
    "hyperparameters": {}
  },
  "expected_result": "...",
  "reason": "..."
}
```

After real evaluation, ARIA supplies KEEP/REJECT, reason, learning, and next_question,
plus experiment/session/revision identity. This can be combined with the next
proposal in one response to reduce event overhead, as in the existing probe.
At budget exhaustion request a final decision without another training proposal.

Maintain the numeric best independently from ARIA's retention of an experiment
as useful evidence. Preserve all rejected results. Thresholded precision/recall
tradeoffs must not be confused with AUPRC ranking improvements.

## 8. Weave and evidence requirements

Every experiment creates a W&B run with session/iteration/parent identity,
hypothesis, configuration, metrics, runtime, deltas, decision, and score provenance.
Log PR data, confusion matrix, importance where available, and real predictions
or reproducible references. Link run IDs and trace IDs both ways where supported.

Desired logical stages:
`aria_analyze_state`, `aria_form_hypothesis`, `aria_design_experiment`,
`validate_experiment`, `execute_training`, `evaluate_result`, `aria_decide`,
`aria_next_iteration`.

IMPORTANT: the successful probe traced receipt/validation/training/final receipt.
It did NOT expose ARIA's internal native reasoning calls. Do not create fake spans
that imply you instrumented those internal calls. Seek documented native tracing
support. If unavailable, trace actual external request/wait/response and structured
observation/hypothesis/decision consumption; label those as received ARIA outputs
and link original conversation/artifact evidence. State this limitation honestly.
Store concise ARIA-provided rationales, not invented or claimed hidden reasoning.

Weave should show a genuine inspectable trajectory, not decorative logging.
Integration errors must be visible; avoid silently reporting success when uploads fail.

## 9. Backend, persistence, CLI, and UI

Build a durable state machine for sessions and experiments, SQLite initially.
Support start, pause/cancel, resume, status, history, details, and verified replay.
Persist hypotheses, exact configurations, results, decisions, artifact versions,
W&B/Weave links, errors, and timestamps. A refresh or process restart must not lose
history. Stream progress with SSE or use simple polling; no need for extra services.
Reset should create a new session while preserving evidence, not delete cloud data.

Provide CLI for data setup, baseline, research loop, resume, replay export, and
final official evaluation. The loop must operate independently of the UI.

Frontend: polished scientific console, dark if appropriate, not a generic admin
template. Primary panel label must be **ARIA RESEARCHER** everywhere. Show:

- Published benchmark: 53.3% AUPRC, clearly identified as official test reference.
- Actual baseline and current validation best, experiment count, budget, status.
- ARIA Observation, Hypothesis, Experiment, Decision, Learning, Next Question.
- Actual experiment trajectory, regressions included, clear split/score labels.
- Experiment details: model/features, configuration, metrics, error analysis,
  rationale, runtime, W&B run and Weave trace links.
- Dataset context, eligible information timing, and actual verified event count.
- LIVE RUN versus REPLAYING VERIFIED RUN; explicit development/fallback labels.

Replay reads previously completed real records/artifacts; never fabricate a run
to populate the demo. Replaying the synthetic probe must visibly say synthetic.
Footer: `Research prototype using historical public data. Not for operational
wildfire response.` Do not claim lives saved or deploy for dispatch decisions.

## 10. Tests and acceptance

Write meaningful tests and actually run them. Keep network-dependent tests
separate and clearly mark mocks/fixtures. At minimum cover:

1. Metric parity with official implementation, AP versus trapezoidal PR area,
   degenerate labels handled explicitly, no NaN silently accepted.
2. Split/cohort integrity, excluded columns, discovery timing rules,
   train-only preprocessing, test isolation.
3. Strict proposal parsing: unsupported parameters, NaN/Infinity, invalid types,
   unknown keys, arbitrary code/path injection, stale or wrong-session messages.
4. Configuration canonicalization/deduplication, seeds/protocol in identity,
   duplicate events/artifacts, transactional execution claims.
5. Best-score and decision handling: regression retained as evidence does not
   overwrite numeric best; synthetic/validation scores cannot trigger official win.
6. Persistence, restart recovery, cancellation, timeout, failed training,
   exhausted budget, and final-decision handling.
7. W&B/Weave wrappers: required metadata, provenance, secret exclusion, errors
   surfaced, correct run/trace association.
8. Replay equality with stored records, no retraining or new ARIA calls during replay.
9. API and frontend: start/status/details, refresh persistence, accessible controls,
   live updates, error/empty states, correct score labels and links.
10. End-to-end smoke: real lightweight train → measured metric → persistence →
    W&B/Weave evidence when configured → actual ARIA state exchange → second real
    experiment → ARIA decision. Tests using mocked ARIA are unit/integration tests,
    not proof of real ARIA connectivity.

Use a bounded real-data smoke subset if needed, explicitly DEV SCORE. Then run
an official-data baseline and at least two actual ARIA-selected experiments when
data/access/resources permit. Preserve their artifacts for replay. Run frontend
type checking, production build, backend tests, and a browser end-to-end check.
Record exact commands, outcomes, skipped checks, and reasons in `TEST_REPORT.md`.

## 11. Build order and completion

1. Inspect files/environment and official protocol; write verified protocol notes.
2. Implement official data adapter/cache, baseline, metrics, and run/trace logging.
3. Generalize the proven ARIA artifact exchange with durable state and validations.
4. Configure a new scoped automation; prove baseline-to-proposal-to-result-to-next
   proposal with real ARIA, keeping the old probe evidence intact.
5. Add CLI/API, minimal UI, persistence/recovery, then polish trajectory and replay.
6. Add supported CoreWeave execution only when access and resource bounds exist.
7. Run tests, produce real replay records and concise demo instructions.

Deliver runnable frontend/backend/CLI, `.env.example` with placeholders, pinned
dependencies, setup/data commands, `README.md` with architecture Mermaid diagram,
`BENCHMARK_PROTOCOL.md`, `TEST_REPORT.md`, and `DEMO.md`. Document the automation
prompt/filter and recovery process so it can be reproduced without chat history.

If external access blocks one component, finish all independent work, report the
specific blocker, and label partial capabilities accurately. Do not stop at a
plan. Do not claim full completion on mocked data or a synthetic benchmark score.

Start by reading the existing probe and protocol source, then build the smallest
real end-to-end wildfire loop before adding extra models or UI polish.
