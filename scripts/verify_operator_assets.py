"""Read back ARIA's report/workspace, model lineage, notifications, and optional Launch session."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import wandb
import wandb_workspaces.workspaces as ws
import wandb_workspaces.reports.v2 as wr
from wildfire_researcher import config,tracking
from wildfire_researcher.state import Store


def main():
    config.load_wandb_credential();api=wandb.Api();out=config.ARTIFACTS_DIR/'operations'
    art=api.artifact(f'{config.WANDB_ENTITY}/{config.WANDB_PROJECT}/aria-operator-retrospective:v1')
    root=Path(art.download(root=str(out/'aria-retrospective-v1')))
    a=json.loads((root/'analysis.json').read_text())
    workspace=ws.Workspace.from_url(a['urls']['workspace'])
    report=wr.Report.from_url(a['urls']['report'])
    assert len(workspace.sections)>=3 and len(report.blocks)>=10
    assert a['weave_audit']['ended_at_present_count']==126
    assert a['decision_consistency']['proposal_count']==17 if 'proposal_count' in a['decision_consistency'] else True
    store=Store(); matched=[]
    for row in a['experiments']:
        sid=row.get('session_id',row.get('session'));eid=row.get('experiment_id')
        if not sid or not eid:raise ValueError('Missing ARIA experiment identity')
        local=store.get_experiment(sid,eid)
        score=row.get('validation_auprc',row.get('val_auprc'))
        if score is None or abs(local['score']-score)>1e-9:raise ValueError('ARIA retrospective metric mismatch')
        matched.append(f'{sid}/{eid}')
    pub=json.loads((out/'preserved-winner'/'publication.json').read_text())
    model=api.artifact(pub['model_artifact']);registered=api.artifact(pub['registry_artifact'])
    assert model.digest==registered.digest==pub['model_digest']
    result={'aria_artifact':art.qualified_name,'aria_artifact_digest':art.digest,
            'report_url':report.url.replace('\\','/'),'report_blocks':len(report.blocks),'workspace_url':workspace.url.replace('\\','/'),
            'workspace_sections':[s.name for s in workspace.sections],
            'retrospective_experiments_matched':len(matched),'registered_model_digest_verified':True,
            'model_artifact':pub['model_artifact'],'registry_artifact':pub['registry_artifact']}
    tracking.write_json(out/'verified_assets.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
