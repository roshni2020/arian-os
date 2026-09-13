"""Launch entrypoint for the existing local Windows compute target via WSL.

The queue runs on WSL; the validated training step runs on the same Windows host.
This is a local CPU adapter, not CoreWeave and not a portable cloud deployment.
"""
import json
import os
import subprocess
import uuid
import hashlib
from pathlib import Path
import wandb


def verify_source_snapshot(snapshot, root):
    """Verify the entire captured Python package, including nested adapters."""
    captured={p.relative_to(snapshot) for p in (snapshot/'wildfire_researcher').rglob('*.py')}
    current={p.relative_to(root) for p in (root/'wildfire_researcher').rglob('*.py')}
    if captured != current:
        raise ValueError('Local application changed; capture a new Launch job version before executing')
    for relative in captured | {Path('scripts/run_launch_step.py')}:
        source=snapshot/relative;local=root/relative
        if not local.is_file() or hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(local.read_bytes()).digest():
            raise ValueError('Local application changed; capture a new Launch job version before executing')


def main():
    with wandb.init(job_type='launch-controller') as run:
        request=dict(run.config)
        root=Path('/mnt/c/AI/Projects/focus')
        snapshot=Path(__file__).resolve().parent
        verify_source_snapshot(snapshot,root)
        token=uuid.uuid4().hex
        inbox=root/'artifacts'/'operations'/'launch-inbox';inbox.mkdir(parents=True,exist_ok=True)
        path=inbox/f'{token}.json';out=inbox/f'{token}-result.json'
        path.write_text(json.dumps(request))
        # Child starts its own measured experiment run. Do not inherit Launch's run id/config.
        env={k:v for k,v in os.environ.items() if not k.startswith('WANDB_')}
        proc=subprocess.run([str(root/'.venv'/'Scripts'/'python.exe'),
            r'C:\AI\Projects\focus\scripts\run_launch_step.py','--request',
            f'C:\\AI\\Projects\\focus\\artifacts\\operations\\launch-inbox\\{token}.json',
            '--output',f'C:\\AI\\Projects\\focus\\artifacts\\operations\\launch-inbox\\{token}-result.json'],
            env=env,cwd=str(root),timeout=1900,check=True)
        result=json.loads(out.read_text());run.summary.update(result)
        run.summary['execution_backend']='W&B Launch / local WSL-to-Windows CPU adapter'
        art=wandb.Artifact(f'launch-result-{run.id}',type='launch-result');art.add_file(str(out),name='result.json')
        run.log_artifact(art)


if __name__=='__main__':main()
