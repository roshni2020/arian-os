# Real ARIA integration test — 2026-09-13

Completed two real ARIA-selected experiments and a final ARIA decision using
synthetic data. This is not a WildfireIA benchmark result.

| Trial | ARIA-selected change | Validation AUPRC | ARIA decision |
|---|---|---:|---|
| Baseline | Fixed setup: 2 features, C=1, unweighted | 0.3573556168800534 | REJECT as incumbent |
| 1 | Use 4 informative features | 0.5396946887587629 | KEEP |
| 2 | Add balanced class weighting | 0.5266460741237637 | REJECT as incumbent |

Trial 2 increased recall from 0.29167 to 0.60417 but increased false positives
from 1 to 52. ARIA retained trial 1 because the objective was validation AUPRC.
All trials used the same fixed split. The worker stopped at its two-experiment budget.

## Verified integration

1. A direct browser conversation with real ARIA produced proposal 1 as a W&B artifact.
2. A W&B Automation was configured after trial 1. A clearly labeled control run
   (`aria-probe-20260913-wake-1`) supplied the initial event; it logged no training metrics.
3. The event invoked ARIA, which read the latest state, kept trial 1, and wrote proposal 2.
4. The local Python worker validated that proposal and trained trial 2.
5. Trial 2's finish event automatically invoked a fresh ARIA conversation, which
   read the updated state and wrote the final REJECT decision. No manual follow-up
   selected trial 2 or requested this final decision.
6. The worker received the final artifact and published status `complete`.

The automation history shows two successful dispatches. Dispatch completion alone
is not proof of an ARIA result; the resulting artifacts and completed worker state
provide that evidence. After testing, the trigger was neutralized with the
nonmatching regex `a^`, preserving automation and conversation history.

## Evidence

- [W&B project](https://wandb.ai/ali-amjad52114-r42/aria-integration-probe)
- [Baseline run](https://wandb.ai/ali-amjad52114-r42/aria-integration-probe/runs/6vtgcf2c)
- [Trial 1](https://wandb.ai/ali-amjad52114-r42/aria-integration-probe/runs/t581viv8)
- [Trial 2](https://wandb.ai/ali-amjad52114-r42/aria-integration-probe/runs/bmg5dqp3)
- [Final decision receipt](https://wandb.ai/ali-amjad52114-r42/aria-integration-probe/runs/5l4alegq)
- [Weave traces](https://wandb.ai/ali-amjad52114-r42/aria-integration-probe/weave/traces)
- [Automation history](https://wandb.ai/ali-amjad52114-r42/aria-integration-probe/automations?tab=history)

Artifact versions in project `ali-amjad52114-r42/aria-integration-probe`:

- `aria-probe-20260913-proposal-1:v0`
- `aria-probe-20260913-proposal-2:v0`
- `aria-probe-20260913-decision-final:v0`

Original ARIA conversation: `01a09a1d-3e87-7c82-b8d5-5b321200cb76`.
Automatically invoked proposal-2 conversation:
`01a09a22-3acd-7e70-a237-97775d913325` (also recorded in artifact metadata).
The recorded test state used `:latest` source labels; the worker now records
immutable version references for future sessions.

Verification found three finished training runs, remote AUPRC matching local state,
`benchmark_comparable=false`, and eight successful Weave traces. Four validator
unit tests passed, covering accepted configurations, duplicates, unsupported or
invalid parameters, and required decisions.

## Remaining work before the full project

- Training ran locally using scikit-learn. CoreWeave execution and W&B Launch
  remain unverified; no active Launch queue/agent was found in this team.
- Weave records actual proposal receipt, validation, training, and decision
  receipt. ARIA's internal observation/hypothesis/design calls are not exposed
  as separate native spans; this probe does not satisfy that stronger tracing
  requirement or fabricate those spans. ARIA's structured outputs and original
  conversations preserve its stated rationale.
- The full WildfireIA dataset, leakage checks, official evaluation reproduction,
  UI, production queueing, retries, and concurrency controls are not built here.
- The prototype validates an allowlisted synthetic experiment configuration;
  this is not a general wildfire leakage or comparability validator.
- Access is through ARIA UI plus W&B Automations and Artifacts. This does not
  establish a direct prompt-to-ARIA MCP tool or a public synchronous ARIA API.

This demonstrates the central sponsor-based control loop without a replacement
LLM researcher. The local worker only executes validated configurations.
