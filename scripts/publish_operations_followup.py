"""Publish verified operator evidence and append it to ARIA's historical report."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import wandb
import wandb_workspaces.reports.v2 as wr
from wildfire_researcher import config,tracking


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-existing',action='store_true');args=parser.parse_args()
    config.load_wandb_credential();out=config.ARTIFACTS_DIR/'operations'
    verified=json.loads((out/'launch'/'verified.json').read_text())
    assets=json.loads((out/'verified_assets.json').read_text())
    sid=verified['session'];prefix=f'{config.WANDB_ENTITY}/{config.WANDB_PROJECT}'
    with sqlite3.connect(config.DATA_DIR/'operations-alerts.sqlite') as db:
        alerts=[{'key':k,'state':s} for k,s in db.execute('select key,state from alerts') if k.startswith(sid+':')]
    tracking.write_json(out/'launch'/'alerts.json',alerts)
    if args.verify_existing:
        art=wandb.Api().artifact(f'{prefix}/{sid}-verified-replay:v0')
        downloaded=Path(art.download(root=str(out/'verified-replay')))
        assert json.loads((downloaded/'replay.json').read_text())==json.loads((config.ARTIFACTS_DIR/sid/'replay.json').read_text())
        assert json.loads((downloaded/'verification.json').read_text())==verified
        reference=art.qualified_name
    else:
      with wandb.init(entity=config.WANDB_ENTITY,project=config.WANDB_PROJECT,
                    name='operator-verified-launch-evidence',job_type='verification',
                    config={'session_id':sid,'test_evaluated':False,'benchmark_comparable':False}) as run:
        art=wandb.Artifact(f'{sid}-verified-replay',type='research-replay',
                           metadata={'session_id':sid,'verified_aria_controllers':3,'test_evaluated':False})
        for path,name in [(config.ARTIFACTS_DIR/sid/'replay.json','replay.json'),
                          (out/'launch'/'verified.json','verification.json'),(out/'launch'/'alerts.json','alerts.json')]:
            art.add_file(str(path),name=name)
        run.log_artifact(art);art.wait()
        reference=art.qualified_name
    report=wr.Report.from_url(assets['report_url'])
    marker=f'Operational follow-up: {sid}'
    text=f'''## {marker}

This independently verified operator follow-up was added after ARIA's fixed 49-run retrospective.
Real ARIA submitted two experiments and its final KEEP decision through W&B Launch:
validation AUPRC **0.1841706764 → 0.4829886184 → 0.4999662448**.
The selected model is full-feature XGBoost, default depth 4, scale_pos_weight 1.5.
The first experiment changed both model and features; the second isolated class weight.
These are validation measurements, not new test scores or benchmark certification.

The three ARIA-submitted controller runs carry W&B's native ARIA thread/turn provenance:
[experiment 1](https://wandb.ai/{prefix}/runs/sfgw1glz),
[experiment 2](https://wandb.ai/{prefix}/runs/9aaytrms),
[final decision](https://wandb.ai/{prefix}/runs/ban896uu).
Local measurements, cloud metrics, proposal contents and model artifact digests were reconciled.
The completed replay and independent verification are preserved as `{reference}`.
The first bootstrap attempt failed before training because of a Windows/WSL file-lock issue;
its identical unmeasured baseline was retried after fixing the working directory.

The historical depth-3 winner was separately reconstructed with exactly matching validation
predictions and registered as `{assets['registry_artifact']}`. Its pinned dataset reference
manifest and model lineage are linked from [the preservation run](https://wandb.ai/{prefix}/runs/swi7lt88).
New experiment runs preserve their own fitted model bundles.

The [research workspace]({assets['workspace_url']}) separates scientific comparisons from the
[operations workspace](https://wandb.ai/{prefix}?nw=r4e1aykiznb).
A persistent local W&B alert monitor submitted real failure, budget-exhaustion and final-decision
alerts during this test. Inbox delivery depends on W&B notification settings. Both Launch and
monitoring use local CPU/processes and must remain running; no CoreWeave execution is claimed.
Internal ARIA reasoning and token costs remain unavailable; the external exchanges are traced in Weave.
'''
    block=wr.MarkdownBlock(text=text)
    matches=[i for i,b in enumerate(report.blocks) if marker in getattr(b,'text','')]
    if matches:report.blocks[matches[0]]=block
    else:report.blocks.append(block)
    report.save()
    check=wr.Report.from_url(report.url.replace('\\','/'))
    assert any(marker in getattr(b,'text','') for b in check.blocks)
    result={'report_url':check.url.replace('\\','/'),'verified_replay_artifact':reference,
            'verified_replay_digest':art.digest,'alerts':alerts}
    tracking.write_json(out/'publication.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
