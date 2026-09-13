"""Print a reproducible ARIA instruction for the session prepared by setup_launch.py."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
setup=json.loads((root/'artifacts'/'operations'/'launch'/'setup.json').read_text())
job=setup['job'];project=job.rsplit('/',1)[0];entity,project_name=project.split('/')
sid=setup['session_id']
print(f'''Control the bounded WildfireIA research session {sid} using W&B Launch.
Use only job {job}, queue {setup['queue']}, entity {entity}, project {project_name},
resource local-process. The job executes validated local CPU training. Budget is
{setup['budget']} ARIA experiments after the fixed baseline. Do not use test data.

Inspect existing queued/running jobs and {project}/{sid}-state:latest first. If no
baseline exists or is queued/running, submit exactly one action=baseline request.
Otherwise continue from the actual immutable state version. Stop if already complete.
For each new measured result, decide KEEP/REJECT, choose the next hypothesis and
experiment, and construct a proposal using state.capabilities.response_contract.
Submit using:
from wandb.sdk.launch import launch_add
launch_add(job={job!r}, entity={entity!r}, project={project_name!r},
    queue_name={setup['queue']!r}, resource='local-process',
    name='{sid}-aria-launch-rN',
    config={{'overrides': {{'run_config': REQUEST}}}})

REQUEST is {{'session_id': {sid!r}, 'action': 'baseline'}} for the fixed baseline,
or {{'session_id': {sid!r}, 'action': 'proposal', 'proposal': PROPOSAL}}.
Monitor the queued controller and its measured experiment until completion before
reading the next state. Never submit duplicate steps. Do not override entrypoints,
resources, commands, or protocol checks. On a failure inspect logs and report the
cause; do not resubmit an uncertain attempt or bypass the validator.
When remaining_budget=0, submit one action=final request with a decision field
matching the final-decision schema in state. Monitor it until session complete.
Publish {sid}-launch-evidence as a research-analysis artifact with immutable state
references, queue item IDs, controller and measured run IDs, proposals, decisions,
actual validation metrics, and explicit confirmation that no test evaluation ran.
Do not invent metrics or claim access to hidden internal reasoning/token usage.
''')
