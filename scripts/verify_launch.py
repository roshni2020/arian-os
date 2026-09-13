"""Verify actual ARIA-authored Launch requests against persisted measurements."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import wandb
from wildfire_researcher import config,tracking
from wildfire_researcher.state import Store


def main():
    p=argparse.ArgumentParser();p.add_argument('--session',required=True);args=p.parse_args()
    config.load_wandb_credential();api=wandb.Api();store=Store()
    session=store.get_session(args.session)
    assert session['status']=='complete' and session['final_evaluation'] is None
    assert session['protocol']['execution_backend']=='wandb-launch'
    exps=store.completed_experiments(args.session)
    assert len(exps)==session['budget']+1
    project=f'{session["wandb_entity"]}/{session["wandb_project"]}'
    controllers=[r for r in api.runs(project,filters={'config.session_id':args.session})
                 if r.config.get('action') in ('proposal','final')]
    assert len(controllers)==session['budget']+1
    evidence=[];final_count=0
    for run in controllers:
        assert run.state=='finished',run.id
        agent=run.config.get('_wb_agent') or {}
        assert agent.get('thread_id') and agent.get('turn_id'),f'{run.id}: missing real ARIA provenance'
        action=run.config['action']
        if action=='proposal':
            proposal=run.config['proposal']
            # The proposal validator fills the optional hyperparameters={} default.
            # Compare all remaining submitted fields exactly, including decisions.
            normalized=json.loads(json.dumps(proposal))
            normalized['experiment'].setdefault('hyperparameters',{})
            matches=[e for e in exps if (e.get('proposal') or {}).get('raw')==normalized]
            assert len(matches)==1,f'{run.id}: request does not match one recorded experiment'
            measured=matches[0]
            remote=api.run(f'{project}/{measured["wandb_run_id"]}')
            assert remote.state=='finished'
            assert abs(remote.summary['validation_auprc']-measured['score'])<1e-12
            model=api.artifact(f'{project}/{args.session}-{measured["id"]}-model:latest')
            detail={'experiment_id':measured['id'],'measured_run_id':remote.id,
                    'validation_auprc':measured['score'],'model_artifact':model.qualified_name,'model_digest':model.digest,
                    'proposal':proposal}
        else:
            final_count+=1
            raw=json.loads((config.ARTIFACTS_DIR/args.session/'decision.json').read_text())
            assert run.config['decision']==raw
            detail={'decision':raw}
        result=api.artifact(f'{project}/launch-result-{run.id}:latest')
        evidence.append({'controller_run_id':run.id,'controller_name':run.name,'state':run.state,
                         'action':action,'aria_provenance':agent,'result_artifact':result.qualified_name,
                         'result_digest':result.digest,**detail})
    assert final_count==1
    state=api.artifact(f'{project}/{args.session}-state:latest')
    result={'session':args.session,'status':session['status'],'test_evaluated':False,
            'best_validation_auprc':session['current_best_auprc'],'state_artifact':state.qualified_name,
            'state_digest':state.digest,'controllers':evidence}
    tracking.write_json(config.ARTIFACTS_DIR/'operations'/'launch'/'verified.json',result)
    print(json.dumps({'session':args.session,'verified_aria_controllers':len(evidence),
                      'best_validation_auprc':session['current_best_auprc'],'test_evaluated':False},indent=2))


if __name__=='__main__':main()
