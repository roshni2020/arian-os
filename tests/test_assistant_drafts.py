"""Reviewed draft admission tests: no workers, network calls or training."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from wildfire_researcher.state import Store, research_state
from wildfire_researcher.assistant.drafts import DraftService, approved_context, digest
from wildfire_researcher import experiments as ex, protocol
from wildfire_researcher.assistant.evidence import evidence_protocol

@pytest.fixture
def store(tmp_path):
    store=Store(tmp_path/'research.sqlite')
    store.create_session(session_id='source',budget=5,aria_mode='connected',research_seed=protocol.RESEARCH_SEED,
                         fast_mode=False,limit_train_samples=None,entity='test',project='test')
    store.update_session('source',status='complete')
    return store

def request(kind='error_proposal', project=None):
    content={'hypothesis':'Fuel may improve recall','experiment':{'model':'xgboost','feature_protocol':'metadata_fuel',
              'weather_days':5,'hyperparameters':{}},'success_criteria':['Higher validation AP'],'tradeoffs':['Longer training']}
    if kind=='study_plan':
        content={'objective':'Compare feature families','experiment_budget':3,'success_criteria':['Higher validation AP'],
                 'steps':['Fuel features','Weather features'],'stopping_conditions':['Budget exhausted']}
    snapshot={'session_id':None if project else 'source','session_revision':None if project else 0,'hash':'frozen-evidence',
              'protocol_fingerprint': evidence_protocol(session={'protocol':protocol.provenance(),'limit_train_samples':None})['protocol_fingerprint'],
              'project_id':project['id'] if project else None,
              'project_snapshot_hash':digest(project['snapshot']) if project else None}
    return {'id':'req-'+kind,'kind':kind,'status':'succeeded','snapshot':snapshot,
            'provenance':{'aria_verified':True},'response':{'draft':content}}

def start(service,draft,**kwargs):
    return service.prepare_start(draft['id'],draft['version_hash'],entity='test',project='test',**kwargs)

def test_create_and_prepare_start_are_atomic_and_idempotent(store):
    service=DraftService(store)
    with ThreadPoolExecutor(max_workers=4) as pool:
        drafts=list(pool.map(lambda _: service.create(request()),range(8)))
    assert len({d['id'] for d in drafts})==1
    with ThreadPoolExecutor(max_workers=4) as pool:
        approved=list(pool.map(lambda _: start(service,drafts[0]),range(8)))
    assert len({d['session'] for d in approved})==1
    assert len(store.list_sessions())==2
    child=store.get_session(approved[0]['session'])
    assert child['budget']==1 and child['aria_mode']=='connected'
    assert child['status']=='created' and store.experiments(child['id'])==[]
    assert store.get_session('source')['budget']==5

def test_manual_import_rejected(store):
    req=request(); req['provenance']={'aria_verified':False,'transport':'manual-import'}
    with pytest.raises(ValueError,match='verified'): DraftService(store).create(req)

def test_version_source_revision_and_active_source_rejected(store):
    service=DraftService(store); draft=service.create(request())
    with pytest.raises(ValueError,match='version'): service.prepare_start(draft['id'],'stale',entity='x',project='y')
    store.update_session('source',status='training')
    with pytest.raises(ValueError,match='active'): start(service,draft)
    store.update_session('source',status='complete',state_revision=1)
    with pytest.raises(ValueError,match='changed'): start(service,draft)
    assert len(store.list_sessions())==1

def test_reject_baseline_repeat_and_subsample_followup(store):
    service=DraftService(store); req=request(); req['response']['draft']['experiment']=ex.BASELINE_EXPERIMENT
    with pytest.raises(ValueError,match='baseline'): service.create(req)
    draft=service.create(request()); store.update_session('source',limit_train_samples=100)
    with pytest.raises(ValueError,match='full-data|protocol changed'): start(service,draft)

def test_source_protocol_change_denied_without_revision_change(store):
    service=DraftService(store); draft=service.create(request())
    changed=copy.deepcopy(store.get_session('source')['protocol'])
    changed['dataset_revision']='unexpected revision'
    with store.connect() as db:
        db.execute('UPDATE sessions SET protocol_json=? WHERE id=?',(json.dumps(changed),'source'))
    with pytest.raises(ValueError,match='protocol changed'): start(service,draft)
    assert len(store.list_sessions())==1

def test_current_executor_protocol_change_denied(store,monkeypatch):
    service=DraftService(store); draft=service.create(request())
    changed=copy.deepcopy(protocol.provenance()); changed['dataset_revision']='new executor revision'
    monkeypatch.setattr(protocol,'provenance',lambda:changed)
    with pytest.raises(ValueError,match='current supported executor'): start(service,draft)
    assert len(store.list_sessions())==1

def project():
    return {'id':'project-a','snapshot':{'task_type':'binary classification'},'compatibility':{'executable':True}}

def test_project_changes_after_draft_require_new_plan(store):
    service=DraftService(store); p=project(); draft=service.create(request('study_plan',p),p)
    changed=copy.deepcopy(p); changed['snapshot']['task_type']='multiclass'
    with pytest.raises(ValueError,match='snapshot changed'): start(service,draft,current_project=changed)
    disabled=copy.deepcopy(p); disabled['compatibility']['executable']=False
    with pytest.raises(ValueError,match='supported executor'): start(service,draft,current_project=disabled)
    approved=start(service,draft,current_project=p)
    assert store.get_session(approved['session'])['budget']==3

def test_project_cannot_be_switched_between_request_and_draft(store):
    service=DraftService(store); p=project(); req=request('study_plan',p)
    switched=copy.deepcopy(p); switched['id']='project-b'
    with pytest.raises(ValueError): service.create(req,switched)

def test_project_cannot_change_between_request_and_draft(store):
    service=DraftService(store); p=project(); req=request('study_plan',p)
    changed=copy.deepcopy(p); changed['snapshot']['task_type']='changed'
    with pytest.raises(ValueError): service.create(req,changed)

def test_approved_context_and_first_proposal_are_enforced(store):
    service=DraftService(store); draft=start(service,service.create(request()))
    sid=draft['session']
    context=approved_context(store,sid)
    assert context['source_session_id']=='source' and context['version_hash']==draft['version_hash']
    state=research_state(store,sid)
    assert state['approved_study_plan']==context
    assert 'first post-baseline experiment' in state['instructions']
    state.update(history=[{'experiment_id':'exp-000','config_key':'baseline'}],remaining_budget=1)
    proposal={'schema_version':1,'session_id':sid,'state_revision':state['state_revision'],'proposal_id':'p',
              'observation':'Baseline evidence','hypothesis':'Fuel signal','expected_result':'Higher AP','reason':'Test fuel',
              'experiment':draft['content']['experiment'],
              'previous_decision':{'experiment_id':'exp-000','decision':'REJECT','reason':'Weak','learning':'Try fuel','next_question':'Fuel?'}}
    assert ex.validate_proposal(proposal,state)['experiment']==draft['content']['experiment']
    proposal['experiment']={**draft['content']['experiment'],'feature_protocol':'all'}
    with pytest.raises(ex.ProposalError) as error: ex.validate_proposal(proposal,state)
    assert error.value.code=='reviewed_configuration_required'
