"""Prepare a restricted-scope local Launch job and an idle research session."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import wandb
from wandb.sdk.launch.create_job import create_job
from wildfire_researcher import config, tracking
from wildfire_researcher.launch_step import create_launch_session


def copy_application_sources(root, stage):
    """Capture Python source only, preserving package subdirectories."""
    for folder in ('wildfire_researcher','scripts'):
        dest=stage/folder;dest.mkdir(exist_ok=True)
        source_root=root/folder
        paths=source_root.rglob('*.py') if folder=='wildfire_researcher' else source_root.glob('*.py')
        for p in paths:
            target=dest/p.relative_to(source_root);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,target)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--new-session',action='store_true',help='Create a new bounded session using the captured job')
    parser.add_argument('--budget',type=int,default=2)
    args=parser.parse_args()
    if not 1 <= args.budget <= 20:parser.error('budget must be between 1 and 20')
    config.load_wandb_credential();api=wandb.Api()
    out=config.ARTIFACTS_DIR/'operations'/'launch';out.mkdir(parents=True,exist_ok=True)
    record_path=out/'setup.json'
    existing=json.loads(record_path.read_text()) if record_path.exists() else None
    source_hash=tracking.sha256_file(config.ROOT/'launch'/'job.py')
    sources=list((config.ROOT/'launch').glob('*.py'))+[config.ROOT/'launch'/'requirements.txt']
    sources+=list((config.ROOT/'wildfire_researcher').rglob('*.py'))+list((config.ROOT/'scripts').glob('*.py'))
    hashes={p.relative_to(config.ROOT).as_posix():tracking.sha256_file(p) for p in sources}
    fingerprint=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    if existing and existing.get('source_fingerprint')==fingerprint:
        if args.new_session:
            existing.update(session_id=create_launch_session(budget=args.budget)['id'],budget=args.budget)
            existing.pop('baseline_queue_item_id',None)
            tracking.write_json(record_path,existing)
        print(record_path.read_text());return
    queue_name='wildfire-local-cpu'
    try:
        queue=api.run_queue(config.WANDB_ENTITY,queue_name)
        queue.type
    except (ValueError,wandb.errors.CommError):
        queue=api.create_run_queue(name=queue_name,type='local-process',entity=config.WANDB_ENTITY)
    if queue.type!='local-process':raise ValueError('Existing queue is not the requested local CPU backend')
    stage=out/f'job-source-{fingerprint[:12]}';stage.mkdir(exist_ok=True)
    for name in ('job.py','requirements.txt'):
        shutil.copy2(config.ROOT/'launch'/name,stage/name)
    # Capture the exact application code alongside the local bridge; no secrets/data/logs.
    copy_application_sources(config.ROOT,stage)
    job=create_job(path=str(stage),job_type='code',entity=config.WANDB_ENTITY,project=config.WANDB_PROJECT,
        name='wildfire-validated-local-step',description='ARIA-controlled local CPU research step; proposal validation, duplicate/budget guards, no test evaluation. Requires the configured WSL-to-Windows host.',
        aliases=['local-cpu'],runtime='3.12',entrypoint='python job.py')
    if job is None:raise RuntimeError('Launch job was not created')
    session={'id':existing['session_id']} if existing and not args.new_session else create_launch_session(budget=args.budget)
    result={'queue':queue_name,'job':job.qualified_name,'job_digest':job.digest,'session_id':session['id'],
            'budget':existing.get('budget',args.budget) if existing and not args.new_session else args.budget,
            'backend':'W&B Launch local-process agent on WSL; Windows CPU trainer',
            'agent_status':existing.get('agent_status','not_started') if existing else 'not_started',
            'entrypoint':'python job.py','bridge_sha256':source_hash,'source_fingerprint':fingerprint,
            'source_sha256':{str(p.relative_to(stage)):tracking.sha256_file(p) for p in stage.rglob('*.py')}}
    tracking.write_json(record_path,result)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},indent=2))


if __name__=='__main__':main()
