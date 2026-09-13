"""HTTP contracts used by AssistantWorkspace; no live ARIA, training or publishing."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from wildfire_researcher import api, config
from wildfire_researcher.state import Store
from wildfire_researcher.assistant import routes
from wildfire_researcher.assistant.requests import AssistantService


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = Store(tmp_path / 'research.sqlite')
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path / 'data')
    monkeypatch.setattr(config, 'ARTIFACTS_DIR', tmp_path / 'artifacts')
    monkeypatch.setattr(api, '_store', store)
    monkeypatch.setattr(api, '_workers', {})
    store.create_session(session_id='session', budget=2, aria_mode='connected', research_seed=1,
                         fast_mode=False, limit_train_samples=None, entity='test', project='test')
    for index in range(2):
        exp = store.claim_experiment('session', experiment={'model':'logistic_regression', 'feature_protocol':'metadata',
            'weather_days':5, 'hyperparameters':{'C':index + 1}}, config_key=str(index), controller='aria',
            proposal=None, proposal_source=None, parent_experiment_id=None, change_summary='test')
        store.update_experiment('session', exp['id'], status='complete', decision='KEEP', result={
            'split':'val (2019)', 'score_kind':'VALIDATION_AUPRC', 'validation_auprc':.2 + .1 * index,
            'seed':1, 'train_size':100, 'val_size':20,
            'error_breakdowns':{'state':[{'group':'CA', 'count':12, 'recall':.3}]}})
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected live side effect')
    svc = AssistantService(store, transport=SimpleNamespace(dispatch=forbidden, poll=forbidden))
    monkeypatch.setattr(routes, 'assistant', lambda: svc)
    monkeypatch.setattr(api, '_start_worker', forbidden)
    spawned = []
    monkeypatch.setattr(routes, 'spawn', lambda key, work: spawned.append((key, work)))
    return SimpleNamespace(store=store, svc=svc, client=TestClient(api.app), spawned=spawned)


def request_body(kind='ask', **extra):
    return {'kind':kind, 'session_id':'session', 'experiment_ids':['exp-000','exp-001'],
            'question':'Explain these validation results', 'idempotency_key':'request-' + kind, **extra}


def test_all_request_kinds_save_without_training_or_dispatch_when_unverified(env):
    before = env.store.get_session('session'), env.store.experiments('session')
    for kind in ['ask', 'error_proposal', 'study_plan', 'report']:
        body = request_body(kind, **({'group':{'dimension':'state','group':'CA'}} if kind == 'error_proposal' else {}))
        result = env.client.post('/api/assistant/requests', json=body)
        assert result.status_code == 200, result.text
        item = result.json()
        assert item['status'] == 'queued' and item['snapshot']['evidence']
        assert env.client.post('/api/assistant/requests', json=body).json()['id'] == item['id']
    assert not env.spawned
    assert (env.store.get_session('session'), env.store.experiments('session')) == before
    assert len(env.client.get('/api/assistant/requests?session_id=session').json()['items']) == 4


def test_get_endpoints_do_not_dispatch_or_poll(env, monkeypatch):
    request = env.client.post('/api/assistant/requests', json=request_body()).json()
    monkeypatch.setattr(env.svc, 'capability', lambda: {'verified':True,'reason':'test-only'})
    for path in ['/capabilities', '/requests?session_id=session', '/requests/' + request['id'],
                 '/verifications?session_id=session', '/reports?session_id=session', '/findings?session_id=session']:
        response = env.client.get('/api/assistant' + path)
        assert response.status_code == 200, response.text
    assert not env.spawned
    assert env.svc.get(request['id'])['status'] == 'queued'


def test_verified_request_schedules_only_assistant_worker_and_cancel_stays_cancelled(env, monkeypatch):
    monkeypatch.setattr(env.svc, 'capability', lambda: {'verified':True,'reason':'test-only'})
    request = env.client.post('/api/assistant/requests', json=request_body()).json()
    assert env.spawned == [('assistant-recovery', routes.process_request)]
    cancelled = env.client.post('/api/assistant/requests/' + request['id'] + '/cancel', json={})
    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'cancelled'
    assert env.client.get('/api/assistant/requests/' + request['id']).json()['status'] == 'cancelled'


def test_manual_response_cannot_become_executable_draft(env):
    request = env.client.post('/api/assistant/requests', json=request_body('study_plan')).json()
    payload = {'schema_version':1,'request_id':request['id'],'snapshot_hash':request['snapshot']['hash'],
        'kind':'study_plan','claims':[], 'assumptions':[], 'missing_evidence':[],
        'draft':{'objective':'Investigate validation quality', 'steps':[], 'success_criteria':'Higher validation AP',
                 'experiment_budget':2,'stopping_conditions':'Stop at budget'}}
    env.svc.import_response(request['id'], payload)
    response = env.client.post('/api/assistant/requests/' + request['id'] + '/draft', json={})
    assert response.status_code == 409 and 'manual imports remain review-only' in response.text
    assert len(env.store.list_sessions()) == 1 and not env.spawned


def test_verification_contract_and_explicit_frozen_start(env):
    body = {'session_id':'session','baseline_id':'exp-000','candidate_id':'exp-001','seeds':[17,42],
            'max_runs':4,'idempotency_key':'verification'}
    response = env.client.post('/api/assistant/verifications', json=body)
    assert response.status_code == 200, response.text
    study = response.json()
    assert study['status'] == 'draft' and len(study['children']) == 4 and not env.spawned
    assert env.client.post('/api/assistant/verifications', json=body).json()['id'] == study['id']
    url = '/api/assistant/verifications/' + study['id']
    assert env.client.post(url + '/start', json={'plan_hash':'wrong'}).status_code == 409
    assert not env.spawned
    assert env.client.post(url + '/start', json={'plan_hash':study['plan_hash']}).status_code == 200
    assert len(env.spawned) == 1 and env.spawned[0][0].startswith('verify-')
    assert env.client.post(url + '/cancel', json={}).status_code == 200
    assert env.client.post(url + '/start', json={'plan_hash':study['plan_hash']}).json()['status'] == 'cancelled'
    assert len(env.spawned) == 1


def test_findings_refresh_is_explicit_and_search_returns_ui_fields(env):
    assert env.client.get('/api/assistant/findings?session_id=session').json()['items'] == []
    response = env.client.post('/api/assistant/findings/refresh', json={'session_id':'session'})
    assert response.status_code == 200 and response.json()['indexed'] == 2
    items = env.client.get('/api/assistant/findings?session_id=session&q=logistic').json()['items']
    assert len(items) == 2
    assert {'id','config','metrics','outcome','session_id','experiment_id','limitations'} <= set(items[0])
    assert not env.spawned


def test_local_report_export_is_attachment_without_publication(env):
    response = env.client.post('/api/assistant/reports', json={'session_id':'session','idempotency_key':'report','assistant_request_id':None})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['publication'] is None and report['markdown']
    url = '/api/assistant/reports/' + report['id']
    exported = env.client.get(url + '/export?format=markdown')
    assert exported.status_code == 200 and exported.text == report['markdown']
    assert 'attachment' in exported.headers['content-disposition']
    assert exported.headers['content-type'].startswith('text/markdown')
    assert env.client.get(url + '/export?format=json').json()['id'] == report['id']
    assert env.client.post(url + '/publish', json={'evidence_hash':'wrong'}).status_code == 409
    assert env.client.get(url).json()['publication'] is None and not env.spawned


def test_missing_records_and_invalid_payloads_fail_before_side_effects(env):
    assert env.client.get('/api/assistant/requests/missing').status_code == 404
    assert env.client.post('/api/assistant/requests', json=request_body(kind='not-supported')).status_code == 422
    assert env.client.post('/api/assistant/requests', json=request_body(unexpected=True)).status_code == 422
    assert not env.spawned


def test_publish_body_binds_reviewed_evidence_and_retries_once(env, monkeypatch):
    from wildfire_researcher.assistant import reporting
    report = env.client.post('/api/assistant/reports', json={'session_id':'session','idempotency_key':'publish-report'}).json()
    calls = []
    def create(item, key):
        calls.append(key)
        return 'https://wandb.ai/test/test/reports/verified'
    publisher = SimpleNamespace(lookup=lambda key:None, create=create,
        read=lambda url:{'report_id':report['id'],'evidence_hash':report['evidence_hash']})
    monkeypatch.setattr(reporting, 'WandbReportPublisher', lambda *args:publisher)
    monkeypatch.setattr(config, 'load_wandb_credential', lambda:None)
    url = '/api/assistant/reports/' + report['id'] + '/publish'
    for _ in range(2):
        response = env.client.post(url, json={'evidence_hash':report['evidence_hash']})
        assert response.status_code == 200, response.text
        assert response.json()['publication']['status'] == 'published'
    assert calls == [report['id']]


@pytest.mark.parametrize('seeds', [[True,42], ['17',42], [17.5,42], [17]])
def test_http_seed_types_cannot_bypass_scientific_validation(env, seeds):
    body = {'session_id':'session','baseline_id':'exp-000','candidate_id':'exp-001','seeds':seeds,
            'max_runs':4,'idempotency_key':'invalid-seeds'}
    assert env.client.post('/api/assistant/verifications', json=body).status_code == 422
    assert env.client.get('/api/assistant/verifications?session_id=session').json()['items'] == []
    assert not env.spawned
