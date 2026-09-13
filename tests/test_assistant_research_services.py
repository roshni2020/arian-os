import json
from pathlib import Path

import pytest

from wildfire_researcher import config
from wildfire_researcher.state import Store
from wildfire_researcher.assistant.verification import VerificationService, digest, protocol_identity
from wildfire_researcher.assistant.memory import MemoryService
from wildfire_researcher.assistant.reporting import ReportService


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path / 'data')
    monkeypatch.setattr(config, 'ARTIFACTS_DIR', tmp_path / 'artifacts')
    store = Store(tmp_path / 'research.sqlite')
    store.create_session(session_id='session', budget=2, aria_mode='connected', research_seed=1,
                         fast_mode=False, limit_train_samples=None, entity='test', project='test')
    for index in range(2):
        exp = store.claim_experiment('session', experiment={'model': 'logistic_regression', 'feature_protocol': 'metadata', 'weather_days': 5,
                                                             'hyperparameters': {'C': index + 1}},
                                     config_key=str(index), controller='aria', proposal=None, proposal_source=None,
                                     parent_experiment_id=None, change_summary='test')
        store.update_experiment('session', exp['id'], status='complete', result={
            'split': 'val (2019)', 'score_kind': 'VALIDATION_AUPRC', 'validation_auprc': .2 + .1 * index,
            'seed': 1, 'train_size': 100, 'val_size': 20}, decision='REJECT' if index else 'KEEP',
            decision_learning='DO NOT LEAK narrative secret test AP 0.99')
    return store


def create(service, **kwargs):
    return service.create('session', 'exp-000', 'exp-001', [11, 22], 'create-one', **kwargs)


def runner(**kwargs):
    return {'split': 'val (2019)', 'score_kind': 'VALIDATION_AUPRC', 'validation_auprc': kwargs['experiment']['hyperparameters']['C'] * .1,
            'seed': kwargs['seed'], 'train_size': 100, 'val_size': 20}


def test_draft_is_readonly_and_idempotent(store):
    service = VerificationService(store)
    before = (store.get_session('session'), store.experiments('session'))
    study = create(service)
    assert study['status'] == 'draft' and len(study['children']) == 4
    assert create(service)['id'] == study['id']
    assert (store.get_session('session'), store.experiments('session')) == before
    with pytest.raises(ValueError, match='different inputs'):
        service.create('session', 'exp-000', 'exp-001', [33, 44], 'create-one')


@pytest.mark.parametrize('seeds,budget', [([1], 20), ([1, 1], 20), ([True, 2], 20), ([1, 2, 3], 4), ([1, 2], 100)])
def test_invalid_budget_seeds(store, seeds, budget):
    with pytest.raises(ValueError):
        VerificationService(store).create('session', 'exp-000', 'exp-001', seeds, 'bad', budget)


def test_paired_execution_resumes_only_failed_children(store):
    service = VerificationService(store)
    study = create(service)
    calls = []
    def fail_second(**kwargs):
        calls.append(kwargs['seed'])
        if len(calls) == 2:
            raise RuntimeError('transient')
        return runner(**kwargs)
    failed = service.run(study['id'], fail_second)
    assert failed['status'] == 'failed' and failed['children'][0]['status'] == 'complete'
    resumed = VerificationService(store).run(study['id'], runner)
    assert resumed['status'] == 'complete'
    assert resumed['summary']['complete_pairs'] == 2
    assert resumed['summary']['mean_delta'] == pytest.approx(.1)
    assert not resumed['summary']['claim_eligible']
    service.run(study['id'], lambda **kw: pytest.fail('Completed study reran'))


def test_cancel_blocks_start_and_read_has_no_execution(store):
    service = VerificationService(store)
    study = create(service)
    service.cancel(study['id'])
    assert service.run(study['id'], lambda **kw: pytest.fail('cancelled'))['status'] == 'cancelled'
    assert len(store.experiments('session')) == 2


def test_midrun_cancel_preserves_ledger(store):
    service = VerificationService(store)
    study = create(service)
    def cancel(**kwargs):
        service.cancel(study['id'])
        return runner(**kwargs)
    result = service.run(study['id'], cancel)
    assert result['status'] == 'cancelled'
    assert sum(c['status'] == 'complete' for c in result['children']) == 1


def test_test_result_rejected(store):
    service = VerificationService(store)
    study = create(service)
    result = service.run(study['id'], lambda **kw: {**runner(**kw), 'split': 'test (2020)'})
    assert result['status'] == 'failed'
    assert all(c['result'] is None for c in result['children'])


def test_protocol_change_blocks_run(store):
    service = VerificationService(store)
    study = create(service)
    store.update_session('session', limit_train_samples=50)
    with pytest.raises(ValueError, match='protocol changed'):
        service.run(study['id'], runner)


def test_memory_preserves_negative_results_excludes_narrative_and_exposure(store):
    service = MemoryService(store)
    fp = digest(protocol_identity(store.get_session('session')))
    assert service.search(fp) == []
    service.refresh('session')
    results = service.search(fp)
    assert len(results) == 2 and any(r['outcome'] == 'REJECT' for r in results)
    assert 'DO NOT LEAK' not in json.dumps(results)
    assert service.search('mismatched') == []
    assert len(service.search(fp, 'REJECT')) == 1
    store.update_session('session', final_evaluation={'test_ap': .99})
    assert service.search(fp) == [] and service.refresh('session') == []


def test_immutable_report_export_and_no_test_narrative(store):
    service = ReportService(store)
    report = service.create('session', 'report1')
    store.update_experiment('session', 'exp-001', result={'split': 'test (2020)', 'test_auprc': .999})
    assert service.create('session', 'report1') == report
    assert 'DO NOT LEAK' in service.export(report['id'])  # historical reasoning, report-only
    assert report['evidence']['purpose'] == 'historical_report_only'
    assert '.999' not in service.export(report['id'], 'json')
    assert report['claim_eligible'] is False
    assert service.create('session', 'report2')['evidence_hash'] != report['evidence_hash']


def test_publish_is_idempotent_readback_verified(store):
    service = ReportService(store)
    report = service.create('session', 'report1')
    class Publisher:
        calls = 0
        def lookup(self, key): return None
        def create(self, body, key):
            self.calls += 1
            return 'https://wandb.ai/test/reports/one'
        def read(self, url): return {'report_id': report['id'], 'evidence_hash': report['evidence_hash']}
    publisher = Publisher()
    assert service.publish(report['id'], publisher)['publication']['status'] == 'published'
    service.publish(report['id'], publisher)
    assert publisher.calls == 1


def test_ambiguous_publish_never_blindly_retries(store):
    service = ReportService(store)
    report = service.create('session', 'report1')
    class Publisher:
        calls = 0
        def lookup(self, key): return None
        def create(self, body, key):
            self.calls += 1
            raise TimeoutError('unknown remote outcome')
    publisher = Publisher()
    with pytest.raises(TimeoutError): service.publish(report['id'], publisher)
    with pytest.raises(ValueError, match='unresolved'): service.publish(report['id'], publisher)
    assert publisher.calls == 1


def test_wandb_adapter_verifies_content_without_network(store, monkeypatch):
    from types import SimpleNamespace
    import wandb_workspaces.reports.v2 as wr
    from wildfire_researcher.assistant.reporting import WandbReportPublisher
    report = ReportService(store).create('session', 'adapter')
    identity = {'report_id': report['id'], 'evidence_hash': report['evidence_hash'], 'markdown_hash': digest(report['markdown'])}
    blocks = [SimpleNamespace(text=report['markdown']), SimpleNamespace(text='Publication identity\n\n```json\n' + json.dumps(identity) + '\n```')]
    monkeypatch.setattr(wr.Report, 'from_url', lambda url: SimpleNamespace(blocks=blocks))
    adapter = WandbReportPublisher('test', 'test')
    assert adapter.read('https://wandb.ai/test/reports/one') == identity
    blocks[0].text = 'Changed remote report'
    with pytest.raises(ValueError, match='content differs'):
        adapter.read('https://wandb.ai/test/reports/one')


def test_stale_memory_not_reused(store):
    service = MemoryService(store)
    fp = digest(protocol_identity(store.get_session('session')))
    service.refresh('session')
    exp = store.get_experiment('session', 'exp-001')
    store.update_experiment('session', 'exp-001', result={**exp['result'], 'validation_auprc': .8})
    assert len(service.search(fp)) == 1


def test_report_aria_interpretation_binds_snapshot_and_session(store):
    from wildfire_researcher.assistant.requests import AssistantService
    requests = AssistantService(store)
    request = requests.create('report', 'session', ['exp-000'], 'Summarize', 'narrative')
    request['status'] = 'succeeded'
    request['response'] = {'schema_version': 1, 'request_id': request['id'], 'snapshot_hash': request['snapshot']['hash'],
                           'kind': 'report', 'claims': [], 'assumptions': [], 'missing_evidence': [],
                           'draft': {'title': 'Research', 'limitations': ['Validation only'], 'recommendation': 'Verify the candidate.'}}
    service = ReportService(store)
    report = service.create('session', 'with-narrative', request)
    assert 'Verify the candidate.' in report['markdown']
    assert report['evidence']['aria_narrative']['snapshot']['hash'] == request['snapshot']['hash']
    with pytest.raises(ValueError, match='different report interpretation'):
        service.create('session', 'with-narrative')
    request['session_id'] = 'other'
    with pytest.raises(ValueError, match='this session'):
        service.create('session', 'wrong-scope', request)


def test_busy_execution_persists_actionable_failure(store, monkeypatch):
    from contextlib import contextmanager
    from wildfire_researcher import execution
    @contextmanager
    def busy():
        raise RuntimeError('Another research/evaluation worker is active')
        yield
    monkeypatch.setattr(execution, 'worker_lease', busy)
    service = VerificationService(store)
    study = create(service)
    with pytest.raises(RuntimeError, match='worker is active'):
        service.run(study['id'], runner)
    saved = service.get(study['id'])
    assert saved['status'] == 'failed' and 'worker is active' in saved['error']
    assert all(c['status'] == 'pending' for c in saved['children'])


def test_measured_dispersion_and_frozen_report_verification(store):
    service = VerificationService(store)
    study = create(service)
    assert study['summary']['incomplete'] and study['summary']['expected_pairs'] == 2
    def varying(**kwargs):
        result = runner(**kwargs)
        if kwargs['seed'] == 22 and kwargs['experiment']['hyperparameters']['C'] == 2:
            result['validation_auprc'] = .4
        return result
    completed = service.run(study['id'], varying)
    summary = completed['summary']
    assert summary['min_delta'] == pytest.approx(.1)
    assert summary['max_delta'] == pytest.approx(.3)
    assert summary['std_delta'] == pytest.approx(.1414213562)
    assert not summary['incomplete']
    assert summary['paired_deltas'][0]['baseline_auprc'] == .1
    memory = MemoryService(store)
    memory.refresh('session')
    findings = memory.search(digest(protocol_identity(store.get_session('session'))))
    assert all(f['verification'][0]['id'] == study['id'] for f in findings)
    report = ReportService(store).create('session', 'verified-report')
    assert report['evidence']['verification'][0]['plan'] == completed['plan']
    assert report['evidence']['verification'][0]['children'] == completed['children']
    assert 'Sample standard deviation' in report['markdown']
    store.update_session('session', final_evaluation={'test_ap': .5})
    assert memory.search(digest(protocol_identity(store.get_session('session')))) == []


def test_memory_excludes_fallback_both_ingestion_and_retrieval(store):
    memory = MemoryService(store)
    fp = digest(protocol_identity(store.get_session('session')))
    memory.refresh('session')
    store.update_session('session', aria_mode='fallback')
    assert memory.search(fp) == []
    assert memory.refresh('session') == []


def test_report_reads_existing_official_test_without_evaluation(store, monkeypatch):
    from wildfire_researcher import protocol
    monkeypatch.setattr(protocol, 'load_sealed_test_split', lambda *a, **kw: pytest.fail('Report touched sealed test'))
    store.update_session('session', final_evaluation={
        'score_kind': 'OFFICIAL_TEST_AUPRC', 'experiment_id': 'exp-001', 'mean_test_auprc': .49,
        'std_test_auprc': .02, 'published_test_auprc': .533, 'benchmark_beaten': True, 'claim_eligible': True,
        'reason': 'Private post-test narrative', 'per_seed': [{'seed': 7, 'test_auprc': .49, 'test_auroc': .8, 'fit_notes': 'Do not reuse'}]})
    report = ReportService(store).create('session', 'historical')
    official = report['evidence']['recorded_official_test']
    assert official['mean_test_auprc'] == .49
    assert official['claim_eligible'] is False and official['benchmark_beaten'] is False
    assert 'Previously recorded official-test evaluation' in report['markdown']
    assert 'Private post-test narrative' not in json.dumps(report)
    assert 'Do not reuse' not in json.dumps(report)
    assert report['evidence']['purpose'] == 'historical_report_only'


def test_memory_skips_deleted_sources_and_stale_config_protocol(store):
    memory = MemoryService(store)
    fp = digest(protocol_identity(store.get_session('session')))
    memory.refresh('session')
    original = store.get_experiment
    store.get_experiment = lambda *args: (_ for _ in ()).throw(KeyError('removed'))
    assert memory.search(fp) == []
    store.get_experiment = original
    with store.connect() as db:
        db.execute("UPDATE experiments SET experiment_json=? WHERE id='exp-001'", (json.dumps({'model': 'changed'}),))
    assert len(memory.search(fp)) == 1
    store.update_session('session', limit_train_samples=15)
    assert memory.search(fp) == []
    store.get_session = lambda *args: (_ for _ in ()).throw(KeyError('removed'))
    assert memory.search(fp) == []


def test_memory_skips_removed_verification_reference(store):
    verification = VerificationService(store)
    study = verification.run(create(verification)['id'], runner)
    memory = MemoryService(store)
    memory.refresh('session')
    with verification.db() as db:
        db.execute(f'DELETE FROM {verification.table} WHERE id=?', (study['id'],))
    assert all(not f['verification'] for f in memory.search(digest(protocol_identity(store.get_session('session')))))


def test_memory_prioritizes_source_recency_over_index_order(store):
    memory = MemoryService(store)
    with store.connect() as db:
        db.execute("UPDATE experiments SET updated_at='2026-01-01T00:00:00+00:00' WHERE id='exp-000'")
        db.execute("UPDATE experiments SET updated_at='2026-02-01T00:00:00+00:00' WHERE id='exp-001'")
    entries = memory.refresh('session')
    # Reverse indexing order: newest source first, oldest last.
    with memory.db() as db:
        db.execute(f'DELETE FROM {memory.table}')
    for entry in sorted(entries, key=lambda f: f['source_revision'], reverse=True):
        memory.insert(entry, entry['input_hash'])
    assert memory.search(digest(protocol_identity(store.get_session('session'))), limit=1)[0]['experiment_id'] == 'exp-001'


def test_report_reasoning_is_bounded_and_never_retrieved_as_memory(store):
    store.update_experiment('session', 'exp-001', decision_reason='reason ' * 1000,
                            proposal={'hypothesis': 'Try fewer features', 'raw': 'not reproduced'})
    report = ReportService(store).create('session', 'reasoning')
    entry = next(e for e in report['evidence']['experiments'] if e['id'] == 'exp-001')
    assert len(entry['recorded_reasoning']['decision_reason']) == 4000
    assert entry['recorded_reasoning']['proposal_hypothesis'] == 'Try fewer features'
    assert 'report-only' in report['markdown']
    memory = MemoryService(store)
    findings = memory.refresh('session')
    assert 'Try fewer features' not in json.dumps(findings)


def test_report_v2_resolves_only_cited_frozen_cells_in_export(store):
    from wildfire_researcher.assistant.requests import AssistantService
    request = AssistantService(store).create('report', 'session', ['exp-000'], 'Summarize', 'citation-report')
    cited = next(e for e in request['snapshot']['evidence'] if e['path'] == 'result.validation_auprc')
    uncited = next(e for e in request['snapshot']['evidence'] if e['path'] == 'updated_at')
    request.update(status='succeeded', response={
        'schema_version': 1, 'request_id': request['id'], 'snapshot_hash': request['snapshot']['hash'], 'kind': 'report',
        'claims': [{'text': 'Recorded validation AP is 0.2.', 'citations': [cited['id']]}],
        'assumptions': [], 'missing_evidence': [],
        'draft': {'title': 'Report', 'limitations': ['Seed reliability is unknown.'], 'recommendation': 'Verify.'}})
    service = ReportService(store)
    report = service.create('session', 'v2-cited', request)
    exported = service.export(report['id'])
    assert report['template_version'] == 2
    assert f'| {cited["id"]} | session | exp-000 | result.validation_auprc | 0.2 |' in exported
    assert uncited['id'] not in exported
    assert 'Seed reliability is unknown.' in exported
    assert 'Weather days | Hyperparameters' in exported
    assert '{"C": 1}' in exported


def test_report_tables_escape_untrusted_cells(store):
    from wildfire_researcher.assistant.reporting import markdown
    evidence = ReportService(store).create('session', 'table-escape')['evidence']
    evidence['experiments'][0]['config']['model'] = '<b>unsafe</b>|![x](https://example.invalid)\nnext'
    rendered = markdown(evidence)
    assert '<b>unsafe' not in rendered
    assert '&lt;b&gt;unsafe&lt;/b&gt;\\|' in rendered
    assert '!\\[x\\]' in rendered


def test_report_does_not_label_unverified_import_as_aria(store):
    from wildfire_researcher.assistant.reporting import markdown
    from wildfire_researcher.assistant.requests import AssistantService
    request = AssistantService(store).create('report', 'session', ['exp-000'], 'Summarize', 'unverified-import')
    request.update(status='succeeded', provenance={'aria_verified': False}, response={
        'schema_version': 1, 'request_id': request['id'], 'snapshot_hash': request['snapshot']['hash'], 'kind': 'report',
        'claims': [], 'assumptions': [], 'missing_evidence': [],
        'draft': {'title': 'Report', 'limitations': ['Validation only'], 'recommendation': 'Verify.'}})
    report = ReportService(store).create('session', 'imported-report', request)
    assert '## Imported interpretation (ARIA origin unverified)' in report['markdown']
    assert 'Imported draft limitations:' in report['markdown']
    assert '## ARIA interpretation' not in report['markdown']
    assert 'ARIA draft limitations:' not in report['markdown']
    report['evidence']['aria_narrative']['provenance']['aria_verified'] = True
    verified = markdown(report['evidence'])
    assert '## ARIA interpretation' in verified and 'ARIA draft limitations:' in verified
