import copy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from wildfire_researcher.assistant.requests import AssistantService

class FakeStore:
    def __init__(self, path): self.path = path
    def get_session(self, sid):
        if sid != 's': raise KeyError(sid)
        return {'state_revision': 2, 'final_evaluation': {'secret_test_score': .99}}
    def get_experiment(self, sid, eid):
        if sid != 's' or eid != 'e': raise KeyError(eid)
        return {'updated_at': 'today', 'experiment': {'model':'xgboost'},
                'result': {'split':'val (2019)','score_kind':'VALIDATION_AUPRC','validation_auprc':.4, 'test_score':.99,
                           'error_breakdowns':{'state':[{'group':'CA','count':12,'recall':.3}]}}}

@pytest.fixture
def service(tmp_path): return AssistantService(FakeStore(tmp_path / 'research.sqlite'))
def create(service, key='key'):
    return service.create('ask', 's', ['e'], 'Explain the result', key)
def response(request):
    ev = next(e for e in request['snapshot']['evidence'] if e['path']=='result.validation_auprc')
    return {'schema_version':1,'request_id':request['id'],'snapshot_hash':request['snapshot']['hash'],
            'kind':'ask','claims':[{'text':'Validation AP is 0.4','citations':[ev['id']]}],
            'assumptions':[], 'missing_evidence':[], 'draft':None}

def test_idempotency_survives_restart_and_rejects_changed_input(service):
    a = create(service)
    b = create(AssistantService(service.store))
    assert a == b
    with pytest.raises(ValueError): service.create('ask','s',['e'],'different','key')

def test_concurrent_create_is_one_record(service):
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(lambda _: create(service)['id'], range(12)))
    assert len(set(ids)) == 1

def test_snapshot_excludes_test_data_and_wrong_scope(service):
    request = create(service)
    assert 'test_score' not in str(request['snapshot'])
    assert request['snapshot']['test_exposed']
    with pytest.raises(KeyError): service.create('ask','s',['bad'],'Question','other')

def test_manual_import_label_and_immutable_response(service):
    r = create(service)
    value = service.import_response(r['id'], response(r), {'transport':'wandb-aria'})
    assert value['provenance']['transport']=='manual-import'
    assert service.import_response(r['id'], response(r)) == value
    with pytest.raises(ValueError): service.verify_transport(r['id'])

def test_wrong_snapshot_unknown_citation_and_number_rejected(service):
    r = create(service)
    for mutation in ('snapshot', 'citation','number'):
        p=response(r)
        if mutation=='snapshot': p['snapshot_hash']='wrong'
        elif mutation=='citation': p['claims'][0]['citations']=['fake']
        else: p['claims'][0]['text']='Validation AP is 0.9'
        with pytest.raises(ValueError): service.import_response(r['id'],p)

def test_cancel_blocks_late_response_and_dispatch(service):
    r=create(service)
    service.cancel(r['id'])
    with pytest.raises(ValueError): service.import_response(r['id'],response(r))
    assert service.get(r['id'])['status']=='cancelled'

def test_real_proof_gate_atomic_dispatch_and_poll(service):
    r=create(service)
    class Transport:
        def dispatch(self, request): return {'run_id':request['id']}
        def poll(self, request): return response(request), {'transport':'wandb-aria','artifact_digest':'abc'}
    service.transport=Transport()
    with pytest.raises(ValueError): service.dispatch(r['id'])
    service.dispatch(r['id'],probe=True)
    with pytest.raises(ValueError): service.dispatch(r['id'],probe=True)
    service.poll(r['id'])
    assert service.verify_transport(r['id'])['verified']

def test_ambiguous_dispatch_never_blindly_retries(service):
    r=create(service)
    class Transport:
        def dispatch(self, request): raise RuntimeError('unknown remote result')
    service.transport=Transport()
    with pytest.raises(RuntimeError): service.dispatch(r['id'],probe=True)
    with pytest.raises(ValueError): service.retry(r['id'])

def test_project_plan_without_session(service):
    r=service.create('study_plan',None,[],'Plan this benchmark','plan',project={'id':'p','name':'Benchmark'})
    assert r['project_id']=='p' and r['snapshot']['session_id'] is None


def test_prompt_does_not_recurse_and_permits_sdk(service):
    import re
    from wildfire_researcher.assistant.transport import WandbAssistantTransport
    transport=WandbAssistantTransport('entity','project')
    r=create(service)
    assert re.fullmatch(r'aria-assistant-[a-f0-9]{32}',r['id'])
    assert not re.fullmatch(r'aria-assistant-[a-f0-9]{32}',r['id']+'-response')
    assert len(transport.automation_prompt()) < 4000
    assert '${run_name}-response' in transport.automation_prompt()
    assert 'SDK' in transport.prompt(r) and 'are permitted' in transport.prompt(r)

def test_pending_read_and_recovery_gate(service):
    r=create(service)
    assert service.pending()[0]['status']=='queued'
    with pytest.raises(ValueError): service.recover_once()
    assert service.get(r['id'])['attempt']==0

def test_reconcile_distinguishes_absent_from_existing(service):
    r=create(service)
    class Transport:
        def dispatch(self, request): raise RuntimeError('interrupted')
        def reconcile(self, request): return None
    service.transport=Transport()
    with pytest.raises(RuntimeError): service.dispatch(r['id'],probe=True)
    assert service.reconcile(r['id'])['error']=='confirmed_not_dispatched'
    assert service.retry(r['id'])['status']=='queued'
    with pytest.raises(RuntimeError): service.dispatch(r['id'],probe=True)
    service.transport.reconcile=lambda request: {'run_id':request['id']}
    assert service.reconcile(r['id'])['status']=='waiting'

def test_timeout_is_explicit_and_bounded(service):
    from datetime import datetime, timezone, timedelta
    import json
    r=create(service)
    with pytest.raises(ValueError): service.timeout(r['id'])
    r.update(status='waiting',updated_at=(datetime.now(timezone.utc)-timedelta(seconds=901)).isoformat())
    with service.db.connect() as db:
        db.execute('UPDATE assistant_requests SET status=?,body=? WHERE id=?',('waiting',json.dumps(r),r['id']))
    assert service.timeout(r['id'])['status']=='timed_out'
    with pytest.raises(ValueError): service.retry(r['id'])

def test_explicit_wrong_metric_citation_rejected(service):
    r=create(service)
    p=response(r)
    p['claims'][0]['text']='Validation AUROC is 0.4'
    with pytest.raises(ValueError,match='metric'): service.import_response(r['id'],p)

def test_explicit_wrong_run_citation_rejected(service):
    r=create(service)
    r['snapshot']['experiment_ids'].append('exp-other')
    p=response(r)
    p['claims'][0]['text']='exp-other validation AP is 0.4'
    from wildfire_researcher.assistant.contracts import validate_response
    with pytest.raises(ValueError,match='run'): validate_response(p,r)

def test_source_identity_numbers_are_not_metric_evidence(service):
    r=create(service)
    p=response(r)
    p['claims'][0]['text']='Validation AP is 2019'
    with pytest.raises(ValueError): service.import_response(r['id'],p)

def test_idempotent_retry_keeps_original_retrieved_snapshot(service):
    r=service.create('study_plan',None,[],'Plan','plan-key',project={'id':'p','name':'Before'})
    again=service.create('study_plan',None,[],'Plan','plan-key',project={'id':'p','name':'After'},
                         findings=[{'id':'new-discovery'}])
    assert again==r
    assert all(e['value'] != 'After' for e in again['snapshot']['evidence'])

def test_timed_out_requests_do_not_reenter_automatic_recovery(service):
    from datetime import datetime, timezone, timedelta
    r=create(service)
    r.update(status='waiting',dispatched_at=(datetime.now(timezone.utc)-timedelta(seconds=901)).isoformat())
    with service.db.connect() as db:
        db.execute('UPDATE assistant_requests SET status=?,body=? WHERE id=?',('waiting',__import__('json').dumps(r),r['id']))
    service.timeout(r['id'])
    assert service.pending()==[]

def test_reconciliation_does_not_extend_request_timeout(service):
    from datetime import datetime, timezone, timedelta
    r=create(service)
    r.update(status='dispatched',dispatched_at=(datetime.now(timezone.utc)-timedelta(seconds=901)).isoformat())
    with service.db.connect() as db:
        db.execute('UPDATE assistant_requests SET status=?,body=? WHERE id=?',('dispatched',__import__('json').dumps(r),r['id']))
    service.transport=type('Transport',(),{'reconcile':lambda self,request:{'run_id':request['id']}})()
    service.reconcile(r['id'])
    assert service.timeout(r['id'])['status']=='timed_out'

def test_transport_dispatch_isolates_existing_wandb_run(service,monkeypatch):
    import sys
    from types import SimpleNamespace
    from wildfire_researcher.assistant.transport import WandbAssistantTransport
    from wildfire_researcher import config
    request=create(service); calls=[]
    class Artifact:
        def __init__(self,name,type): self.name=name+':v0'; self.digest='digest'; self.type=type; self.version='v0'
        def add_file(self,path,name):
            import json
            body=json.loads(open(path,encoding='utf-8').read())
            assert body['id']==request['id'] and name=='input.json'
        def wait(self): pass
    class Run:
        id=request['id']
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def log_artifact(self,artifact): return artifact
    live=object()
    fake=SimpleNamespace(init=lambda **kw: calls.append(kw) or Run(),Artifact=Artifact,run=live)
    monkeypatch.setitem(sys.modules,'wandb',fake)
    monkeypatch.setattr(config,'load_wandb_credential',lambda:None)
    output=WandbAssistantTransport('entity','project').dispatch(request)
    assert calls[0]['reinit']=='create_new' and fake.run is live
    assert calls[0]['job_type']=='aria-assistant-request'
    assert output['artifact_ref'].endswith(request['id']+'-input:v0')


def test_invalid_live_response_is_terminal_and_preserves_artifact(service):
    r=create(service)
    class Transport:
        def dispatch(self,request): return {'run_id':request['id']}
        def poll(self,request):
            payload=response(request); payload['snapshot_hash']='wrong'
            return payload,{'transport':'wandb-aria','artifact_ref':'entity/project/output:v3','artifact_digest':'digest'}
    service.transport=Transport()
    service.dispatch(r['id'],probe=True)
    failed=service.poll(r['id'])
    assert failed['status']=='failed' and failed['error']=='response_invalid'
    assert 'snapshot' in failed['error_detail']
    assert failed['provenance']['artifact_ref'].endswith(':v3')
    assert service.pending()==[]
    with pytest.raises(ValueError): service.retry(r['id'])
    with pytest.raises(ValueError): service.reconcile(r['id'])
    assert service.poll(r['id'])==failed

def test_artifact_alias_resolves_to_immutable_version():
    from wildfire_researcher.assistant.transport import immutable_artifact_ref
    from types import SimpleNamespace
    assert immutable_artifact_ref('e','p',SimpleNamespace(name='output:latest',version='v7'))=='e/p/output:v7'
    with pytest.raises(ValueError): immutable_artifact_ref('e','p',SimpleNamespace(name='output:latest',version='latest'))

def test_exclusions_are_frozen_idempotent_and_change_request_identity(service):
    r=service.create('ask','s',['e'],'Question','exclude',excluded_finding_ids=['b','a','a'])
    assert r['snapshot']['excluded_finding_ids']==['a','b']
    assert service.create('ask','s',['e'],'Question','exclude',excluded_finding_ids=['a','b'])==r
    with pytest.raises(ValueError,match='Idempotency'):
        service.create('ask','s',['e'],'Question','exclude',excluded_finding_ids=['a'])
    with pytest.raises(ValueError): service.create('ask','s',['e'],'Question','invalid',excluded_finding_ids=['x']*101)

def test_project_protocol_identity_requires_server_executable_flag():
    from wildfire_researcher.assistant.evidence import evidence_protocol
    from wildfire_researcher import protocol
    p={'compatibility':{'executable':True}}
    assert evidence_protocol(project=p)==evidence_protocol(session={'protocol':protocol.provenance(),'limit_train_samples':None})
    assert evidence_protocol(project={'compatibility':{'executable':False}})['protocol_fingerprint'] is None
    assert evidence_protocol(project={'compatibility':{'executable':'true'}})['protocol_fingerprint'] is None

def test_excluded_and_missing_findings_do_not_enter_snapshot(tmp_path):
    from wildfire_researcher.state import Store
    from wildfire_researcher.assistant.evidence import build_snapshot,evidence_protocol
    from wildfire_researcher import protocol
    store=Store(tmp_path/'research.sqlite')
    source=store.create_session(session_id='historical',budget=1,aria_mode='connected',research_seed=protocol.RESEARCH_SEED,
        fast_mode=False,limit_train_samples=None,entity='e',project='p')
    store.claim_experiment('historical',experiment={'model':'logistic_regression'},config_key='key',controller='ARIA',proposal=None,proposal_source=None,parent_experiment_id=None,change_summary='test')
    project={'id':'p','snapshot':{},'compatibility':{'executable':True}}
    fingerprint=evidence_protocol(project=project)['protocol_fingerprint']
    findings=[{'id':'finding-1','session_id':'historical','experiment_id':'exp-000','protocol_fingerprint':fingerprint,
               'outcome':'REJECT','metrics':{'validation_auprc':.4}}]
    included=build_snapshot(store,None,[],project=project,findings=findings)
    excluded=build_snapshot(store,None,[],project=project,findings=findings,excluded_finding_ids=['finding-1'])
    assert any(e['path'].startswith('findings.') for e in included['evidence'])
    assert not any(e['path'].startswith('findings.') for e in excluded['evidence'])
    findings[0]['session_id']='missing'
    missing=build_snapshot(store,None,[],project=project,findings=findings)
    assert not any(e['path'].startswith('findings.') for e in missing['evidence'])
    assert included['hash']!=excluded['hash']


def test_unknown_subgroup_dimension_and_group_rejected(service):
    for subgroup in ({'dimension':'by_state','group':'CA'}, {'dimension':'state','group':'missing'}):
        with pytest.raises(ValueError,match='absent'):
            service.create('error_proposal','s',['e'],'Explain this group',str(subgroup),subgroup=subgroup)
    valid=service.create('error_proposal','s',['e'],'Explain this group','valid-group',subgroup={'dimension':'state','group':'CA'})
    assert any('error_breakdowns.state.' in e['path'] for e in valid['snapshot']['evidence'])

def test_subgroup_claim_cannot_cite_only_global_metrics(service):
    from wildfire_researcher.assistant.contracts import validate_response
    r=service.create('ask','s',['e'],'Explain CA','group-ask',subgroup={'dimension':'state','group':'CA'})
    payload=response(r)
    payload['claims'][0]['text']='CA validation AP is 0.4'
    with pytest.raises(ValueError,match='Subgroup'): validate_response(payload,r)

def test_finding_metric_citation_accepts_only_exact_metric_key(service):
    from wildfire_researcher.assistant.contracts import validate_response
    r=create(service)
    r['snapshot']['evidence'].append({'id':'finding-metric','session_id':'older','experiment_id':'other',
        'path':'findings.finding-one.metrics','value':{'validation_auprc':0.25}})
    p=response(r); p['claims']=[{'text':'Prior validation AP is 0.25','citations':['finding-metric']}]
    assert validate_response(p,r)==p
    p['claims'][0]['text']='Prior validation AUROC is 0.25'
    with pytest.raises(ValueError,match='metric'): validate_response(p,r)

def test_verified_absence_sentence_does_not_relabel_global_finding_as_subgroup(service):
    from wildfire_researcher.assistant.contracts import validate_response
    r=service.create('ask','s',['e'],'Explain CA','absence',subgroup={'dimension':'state','group':'CA'})
    r['snapshot']['evidence'].append({'id':'prior','session_id':'old','experiment_id':'exp-012',
        'path':'findings.prior.metrics','value':{'validation_auprc':0.4}})
    p=response(r); p['claims']=[{'text':'The overall validation AP was 0.4. No California subgroup cells are recorded for exp-012 in this snapshot.',
                              'citations':['prior']}]
    assert validate_response(p,r)==p
    r['snapshot']['evidence'].append({'id':'actual-group','session_id':'old','experiment_id':'exp-012',
        'path':'result.error_breakdowns.state.0.recall','value':0.2})
    with pytest.raises(ValueError,match='absence'): validate_response(p,r)

def test_false_absence_cannot_launder_positive_group_claim(service):
    from wildfire_researcher.assistant.contracts import validate_response
    r=service.create('ask','s',['e'],'Explain CA','absence-positive',subgroup={'dimension':'state','group':'CA'})
    r['snapshot']['evidence'].append({'id':'prior','session_id':'old','experiment_id':'exp-012',
        'path':'findings.prior.metrics','value':{'validation_auprc':0.4}})
    p=response(r); p['claims']=[{'text':'CA validation AP was 0.4. No California subgroup cells are recorded for exp-012 in this snapshot.',
                              'citations':['prior']}]
    with pytest.raises(ValueError,match='Subgroup'): validate_response(p,r)
    p['claims'][0]['text']='The overall validation AP was 0.4. No California subgroup cells are recorded for unknown in this snapshot.'
    with pytest.raises(ValueError,match='absence'): validate_response(p,r)
