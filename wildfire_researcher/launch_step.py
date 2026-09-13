"""Execute one ARIA-submitted Launch action with the existing research safeguards.

Only sessions explicitly created for Launch accept these requests. No arbitrary
commands, paths, test evaluation, or unvalidated configuration can be requested.
"""
from . import config, experiments, protocol
from .execution import exclusive
from .loop import ResearchLoop, change_summary, make_aria
from .state import Store, research_state, new_session_id


def validate_request(request, session):
    if set(request) - {'session_id','action','proposal','decision'}:
        raise ValueError('Unsupported Launch request fields')
    if session['id'] != request.get('session_id') or session['protocol'].get('execution_backend') != 'wandb-launch':
        raise ValueError('Request does not target a Launch session')
    if session['aria_mode'] != 'connected' or session['limit_train_samples']:
        raise ValueError('Launch requires a connected full-data session')
    if request.get('action') not in ('baseline','proposal','final'):
        raise ValueError('Unsupported Launch action; test evaluation is not available')
    if session['cancel_requested'] or session['status'] in ('complete','cancelled'):
        raise ValueError('Session is closed or cancelled')


@exclusive
def execute_request(request):
    store=Store(); session=store.get_session(request['session_id'])
    validate_request(request,session)
    config.load_wandb_credential()
    loop=ResearchLoop(store,session['id'],make_aria(session,config.ARTIFACTS_DIR/session['id']/'aria'))
    state=research_state(store,session['id'])
    action=request['action']
    if action=='baseline':
        rows=store.experiments(session['id'])
        if not rows:
            loop.run_baseline()
        elif len(rows)==1 and rows[0]['status']=='failed' and rows[0]['score'] is None:
            loop.run_claimed_experiment(rows[0],'awaiting_aria_proposal')
        else:raise ValueError('Baseline already exists')
    elif action=='proposal':
        if not store.completed_experiments(session['id']):raise ValueError('Baseline required')
        with loop.aria_context():
            raw=request['proposal']
            loop.receive_aria_output('launch-proposal',raw,{'artifact_ref':None,'artifact_metadata':{'transport':'W&B Launch run config'}})
            valid=loop.validate_experiment(raw,state)
            last=store.completed_experiments(session['id'])[-1]
            loop.record_aria_decision(last['id'],valid['previous_decision'],'W&B Launch submitted configuration')
        store.record_aria_message(session['id'],direction='inbound',kind='proposal',
            artifact_ref=None,artifact_digest=None,state_revision=state['state_revision'],accepted=True,feedback=None,payload=raw)
        claimed=store.claim_experiment(session['id'],experiment=valid['experiment'],config_key=valid['config_key'],
            controller='ARIA',proposal={**{k:valid[k] for k in ('proposal_id','observation','hypothesis','expected_result','reason')},'raw':raw},
            proposal_source='W&B Launch run configuration',parent_experiment_id=last['id'],
            change_summary=change_summary(store.completed_experiments(session['id']),valid['experiment']))
        loop.run_claimed_experiment(claimed,'awaiting_aria_proposal')
    else:
        if state['remaining_budget']>0:raise ValueError('Budget remains; finish the bounded session before finalizing')
        with loop.aria_context():
            loop.receive_aria_output('launch-final-decision',request['decision'],{'artifact_metadata':{'transport':'W&B Launch run config'}})
            decision=experiments.validate_final_decision(request['decision'],state)
            loop.record_aria_decision(decision['experiment_id'],decision,'W&B Launch run configuration')
        store.update_session(session['id'],final_decision=decision)
        store.set_status(session['id'],'complete','ARIA completed its Launch-controlled research loop')
        with loop._run_context('final-decision',-1,'final-decision',{'controller':'worker','benchmark_comparable':False}) as run:
            loop.publish_research_state(run,'complete')
            from .tracking import write_json
            p=write_json(config.ARTIFACTS_DIR/session['id']/'decision.json',request['decision'])
            run.log_artifact(f'{session["id"]}-decision-final','research-decision',{'decision.json':p})
    from .loop import replay_record
    from .tracking import write_json
    write_json(config.ARTIFACTS_DIR/session['id']/'replay.json',replay_record(store,session['id']))
    result=research_state(store,session['id'])
    return {'session_id':session['id'],'status':result['status'],'best_validation_auprc':result['current_best_validation_auprc'],
            'state_artifact':f'{session["wandb_entity"]}/{session["wandb_project"]}/{session["id"]}-state:latest'}


def create_launch_session(budget=2):
    store=Store()
    session=store.create_session(session_id=new_session_id('launch'),budget=budget,aria_mode='connected',
        research_seed=protocol.RESEARCH_SEED,fast_mode=False,limit_train_samples=None,
        entity=config.WANDB_ENTITY,project=config.WANDB_PROJECT)
    import json
    store.update_session(session['id'],protocol_json=json.dumps({**session['protocol'],'execution_backend':'wandb-launch'}))
    return store.get_session(session['id'])
