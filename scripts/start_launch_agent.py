"""Run the official W&B Launch agent on WSL without putting secrets on disk/argv."""
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wildfire_researcher import config

if __name__=='__main__':
    config.load_wandb_credential()
    env=os.environ.copy()
    env['WSLENV']=':'.join(filter(None,[env.get('WSLENV'),'WANDB_API_KEY']))
    # The venv must be first so the agent's child entrypoint uses the same installed SDK.
    cmd=['wsl','-d','Ubuntu-24.04','--','env',
         'PATH=/mnt/c/AI/Projects/focus/.launch-venv/bin:/usr/local/bin:/usr/bin:/bin',
         '/mnt/c/AI/Projects/focus/.launch-venv/bin/python','-m','wandb','launch-agent',
         '-e',config.WANDB_ENTITY,'-q','wildfire-local-cpu','-j','1']
    raise SystemExit(subprocess.call(cmd,env=env))
