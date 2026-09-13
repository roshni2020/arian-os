"""Immutable local research reports and explicit, reconcilable publication."""
import json
import html
import uuid
from urllib.parse import urlparse

from .verification import Records, VerificationService, digest, eligible, protocol_identity
from ..state import now


def markdown(evidence):
    rows = ['# Research report', '', f'Session: `{evidence["session_id"]}`', '',
            f'Recorded research mode: `{evidence.get("research_mode", "unknown")}`. Fallback runs are development-only.', '',
            'Validation research and any previously recorded official-test results are separated below. Benchmark superiority is not certified.', '',
            '| Experiment | Model | Features | Validation AP | Decision |',
            '| --- | --- | --- | ---: | --- |']
    def cell(value):
        text = html.escape(str(value if value is not None else 'Not recorded'), quote=False)
        text = text.replace('\\', '\\\\').replace('\r', ' ').replace('\n', ' ')
        for char in ('|', '[', ']', '`', '*'):
            text = text.replace(char, '\\' + char)
        return text
    for exp in evidence['experiments']:
        rows.append('| ' + ' | '.join(cell(v) for v in (exp['id'], exp['config'].get('model'), exp['config'].get('feature_protocol'), exp['metrics'].get('validation_auprc'), exp['decision'])) + ' |')
    rows += ['', '## Recorded configurations', '',
             '| Experiment | Model | Features | Weather days | Hyperparameters |',
             '| --- | --- | --- | ---: | --- |']
    for exp in evidence['experiments']:
        configuration = exp['config']
        rows.append('| ' + ' | '.join(cell(v) for v in (
            exp['id'], configuration.get('model'), configuration.get('feature_protocol'),
            configuration.get('weather_days'), json.dumps(configuration.get('hyperparameters', {}), sort_keys=True))) + ' |')
    rows += ['', '## Verification', '']
    for study in evidence['verification']:
        rows.append(f'- `{study["id"]}`: {study["status"]}; complete seed pairs: {study["summary"]["complete_pairs"]}; mean validation AP change: {study["summary"]["mean_delta"]}.')
        summary = study['summary']
        rows.append(f'  Sample standard deviation of paired deltas: {summary.get("std_delta")}; '
                    f'range: {summary.get("min_delta")} to {summary.get("max_delta")}; incomplete: {summary.get("incomplete", True)}. '
                    'These describe seed variation, not a generalization confidence interval.')
        for pair in summary['paired_deltas']:
            rows.append(f'  Seed {pair["seed"]}: baseline AP {pair.get("baseline_auprc")}, candidate AP {pair.get("candidate_auprc")}, delta {pair["delta"]}.')
    if not evidence['verification']:
        rows.append('No verification study recorded.')
    rows += ['', '## Recorded selection', '',
             f'Highest recorded validation AP: `{evidence["best_validation_experiment_id"] or "Not recorded"}`. '
             'This ranking is not a verified deployment recommendation.', '',
             f'Discovery experiment budget: {evidence["discovery_budget"]}. Verification has a separate budget.']
    rows += ['', '## Recorded experiment reasoning', '',
             'Historical controller statements are reproduced as recorded, not independently established explanations. '
             'They are report-only and are excluded from research memory and future discovery evidence.', '']
    for exp in evidence['experiments']:
        reasoning = exp.get('recorded_reasoning') or {}
        if reasoning:
            rows.append(f'Experiment `{exp["id"]}` — recorded controller `{exp.get("controller")}`:')
            for field, value in reasoning.items():
                rows.append(f'- {field}: ' + value.replace('\n', ' '))
    rows += ['', '## Limitations', '', '- Validation selection can overfit the validation data.',
             '- Repeated seeds measure seed variation, not generalization to new datasets.',
             '- Recorded controller reasoning and test results are report-only historical evidence, never future discovery context.',
             '- Model paths are recorded references; availability and deployability are not attested.',
             f'- Prior test exposure recorded for this session: {evidence["test_exposed"]}.', '',
             '## Evidence references', '']
    rows += [f'- `{evidence["session_id"]}/{e["id"]}` revision `{e["revision"]}`' for e in evidence['experiments']]
    rows += ['', '## Recorded model references', '']
    rows += [f'- `{e["id"]}`: `{e["model_bundle_path"]}`' for e in evidence['experiments'] if e.get('model_bundle_path')]
    if not any(e.get('model_bundle_path') for e in evidence['experiments']):
        rows.append('No saved model reference recorded.')
    rows += ['', '## Previously recorded official-test evaluation', '']
    official = evidence.get('recorded_official_test')
    if official:
        rows += ['Historical results read from the saved session only; generating this report did not run test evaluation.', '',
                 f'Experiment: `{official.get("experiment_id")}`. Mean test AP: {official.get("mean_test_auprc")}; '
                 f'sample standard deviation: {official.get("std_test_auprc")}.',
                 f'Published reference: {official.get("published_test_auprc")}. '
                 'Exact paper seed reproduction and a fresh confirmatory holdout are not established; superiority remains uncertified.', '',
                 '| Seed | Test AP | Test AUROC |', '| --- | ---: | ---: |']
        rows += [f'| {r.get("seed")} | {r.get("test_auprc")} | {r.get("test_auroc")} |' for r in official['per_seed']]
    else:
        rows.append('No recognized official-test result is recorded in this session. No evaluation was requested.')
    narrative = evidence.get('aria_narrative')
    if narrative:
        verified_aria = (narrative.get('provenance') or {}).get('aria_verified') is True
        interpretation_label = 'ARIA interpretation' if verified_aria else 'Imported interpretation (ARIA origin unverified)'
        limitations_label = 'ARIA draft limitations' if verified_aria else 'Imported draft limitations'
        rows += ['', '## ' + interpretation_label, '',
                 f'Request `{narrative["request_id"]}`, evidence snapshot `{narrative["snapshot"]["id"]}`.',
                 'The interpretation below refers to its frozen request snapshot, which may predate the tables above.', '']
        for claim in narrative['response']['claims']:
            rows.append(claim['text'] + ' [' + ', '.join(claim['citations']) + ']')
        rows += ['', 'Proposed recommendation: ' + narrative['response']['draft']['recommendation'], '',
                 'Assumptions: ' + '; '.join(narrative['response']['assumptions']),
                 'Missing evidence: ' + '; '.join(narrative['response']['missing_evidence'])]
        limitations = narrative['response']['draft']['limitations']
        rows += [limitations_label + ': ' + ('; '.join(limitations) if isinstance(limitations, list) else limitations),
                 '', '### Cited evidence appendix', '',
                 'Values below come from the interpretation’s frozen snapshot, not a newly fetched experiment.', '',
                 '| Evidence ID | Session | Experiment | Field path | Recorded value |',
                 '| --- | --- | --- | --- | --- |']
        cited = {citation for claim in narrative['response']['claims'] for citation in claim['citations']}
        for item in narrative['snapshot']['evidence']:
            if item['id'] in cited:
                rows.append('| ' + ' | '.join(cell(v) for v in (
                    item['id'], item.get('session_id'), item.get('experiment_id'), item.get('path'),
                    json.dumps(item.get('value'), sort_keys=True, ensure_ascii=False))) + ' |')
        if not cited:
            rows.append('| No cited claims | — | — | — | — |')
    return '\n'.join(rows) + '\n'


class ReportService(Records):
    def __init__(self, store):
        super().__init__(store, 'assistant_report_snapshots')

    def create(self, session_id, idempotency_key, aria_response=None):
        narrative = None
        if aria_response is not None:
            from .contracts import validate_response
            from .evidence import digest as snapshot_digest
            if (aria_response.get('kind') != 'report' or aria_response.get('status') != 'succeeded'
                    or aria_response.get('session_id') != session_id
                    or aria_response.get('snapshot', {}).get('session_id') != session_id):
                raise ValueError('Report interpretation must be a successful report request for this session')
            snapshot = aria_response['snapshot']
            if snapshot_digest({k: v for k, v in snapshot.items() if k not in ('id', 'hash', 'created_at')}) != snapshot['hash']:
                raise ValueError('Report interpretation evidence snapshot changed')
            response = validate_response(aria_response['response'], aria_response)
            narrative = {'request_id': aria_response['id'], 'snapshot': snapshot,
                         'response': response, 'provenance': aria_response.get('provenance')}
        # Resolve a retry before reading mutable source evidence.
        with self.db() as c:
            row = c.execute(f'SELECT body FROM {self.table} WHERE session_id=? AND idem=?', (session_id, idempotency_key)).fetchone()
        if row:
            previous = json.loads(row['body'])
            if previous['evidence'].get('aria_narrative') != narrative:
                raise ValueError('Idempotency key already used for a different report interpretation')
            return previous
        session = self.store.get_session(session_id)
        with self.store.connect() as c:
            freeze = c.execute('SELECT 1 FROM final_evaluation_freezes WHERE session_id=?', (session_id,)).fetchone()
        experiments = []
        for exp in self.store.experiments(session_id):
            result = exp.get('result')
            if eligible(result):
                experiments.append({'id': exp['id'], 'revision': exp.get('updated_at'), 'config': exp['experiment'],
                                    'decision': exp.get('decision'),
                                    'controller': exp.get('controller'),
                                    'recorded_reasoning': {
                                        **{key: exp[key][:4000] for key in ('decision_reason', 'decision_learning', 'next_question')
                                           if isinstance(exp.get(key), str) and exp[key]},
                                        **{'proposal_' + key: exp['proposal'][key][:4000] for key in ('observation', 'hypothesis', 'expected_result', 'reason')
                                           if isinstance(exp.get('proposal'), dict) and isinstance(exp['proposal'].get(key), str) and exp['proposal'][key]}},
                                    'metrics': {k: result.get(k) for k in ('validation_auprc', 'validation_auroc', 'seed', 'split', 'score_kind', 'train_size', 'val_size', 'runtime_seconds')},
                                    'model_bundle_path': result.get('model_bundle_path')})
        final = session.get('final_evaluation') or {}
        official = None
        if final.get('score_kind') == 'OFFICIAL_TEST_AUPRC':
            official = {k: final.get(k) for k in ('score_kind', 'experiment_id', 'seeds', 'mean_test_auprc',
                                                  'std_test_auprc', 'published_test_auprc', 'protocol_matched',
                                                  'test_size', 'test_positives', 'prior_test_exposure_sessions')}
            official['per_seed'] = [{k: row.get(k) for k in ('seed', 'test_auprc', 'test_auroc', 'test_f1',
                                                             'test_precision', 'test_recall', 'threshold_from_val')}
                                    for row in final.get('per_seed', [])[:20]]
            official.update(claim_eligible=False, benchmark_beaten=False, purpose='historical_report_only')
        evidence = {'session_id': session_id, 'protocol': protocol_identity(session), 'experiments': experiments,
                    'research_mode': session.get('aria_mode'),
                    'recorded_official_test': official, 'purpose': 'historical_report_only',
                    'aria_narrative': narrative,
                    'discovery_budget': session.get('budget'),
                    'best_validation_experiment_id': max(experiments, key=lambda e: e['metrics'].get('validation_auprc') or -1)['id'] if experiments else None,
                    'verification': [{k: v[k] for k in ('id', 'status', 'plan_hash', 'plan', 'summary', 'children')} for v in VerificationService(self.store).list(session_id)],
                    'test_exposed': bool(freeze or session.get('final_evaluation')), 'claim_eligible': False}
        h = digest(evidence)
        return self.insert({'id': 'report-' + uuid.uuid4().hex, 'session_id': session_id, 'created_at': now(),
                            'input_hash': h, 'evidence_hash': h, 'template_version': 2, 'evidence': evidence,
                            'markdown': markdown(evidence), 'claim_eligible': False, 'publication': None}, idempotency_key)

    def export(self, record_id, format='markdown'):
        report = self.get(record_id)
        if format == 'markdown':
            return report['markdown']
        if format == 'json':
            return json.dumps(report, indent=2, allow_nan=False)
        raise ValueError('Export format must be markdown or json')

    def publish(self, record_id, publisher):
        """Adapter must implement lookup(key), create(report,key), read(url).

        Ambiguous publication is left pending, never blindly retried. The adapter
        must reconcile by immutable key before this method creates a remote report.
        """
        with self.db() as c:
            row = c.execute(f'SELECT body FROM {self.table} WHERE id=?', (record_id,)).fetchone()
            if not row:
                raise KeyError(record_id)
            report = json.loads(row['body'])
            if report['publication'] and report['publication']['status'] == 'published':
                return report
            previous = report['publication']
            report['publication'] = {'status': 'pending', 'key': record_id, 'url': None}
            self.save(report, c)
        url = publisher.lookup(record_id)
        if not url:
            if previous:
                raise ValueError('Publication is unresolved; reconcile remotely before retrying')
            url = publisher.create(report, record_id)
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname != 'wandb.ai' or parsed.username or parsed.password:
            raise ValueError('Publisher returned an invalid W&B report URL')
        remote = publisher.read(url)
        if remote.get('evidence_hash') != report['evidence_hash'] or remote.get('report_id') != record_id:
            raise ValueError('Published report readback does not match immutable evidence')
        with self.db() as c:
            report['publication'] = {'status': 'published', 'key': record_id, 'url': url, 'verified_at': now()}
            self.save(report, c)
        return report


class WandbReportPublisher:
    """Real W&B adapter; construction and local drafts perform no remote writes."""
    def __init__(self, entity, project):
        self.entity, self.project = entity, project

    def lookup(self, key):
        import wandb
        from .. import config
        config.load_wandb_credential()
        title = f'Research evidence · {key}'
        matches = [r for r in wandb.Api().reports(f'{self.entity}/{self.project}', name=title) if r.name == title]
        if len(matches) > 1:
            raise ValueError('Multiple remote reports match this publication key; reconcile manually')
        return matches[0].url.replace('\\', '/') if matches else None

    def create(self, report, key):
        import wandb_workspaces.reports.v2 as wr
        from .. import config
        config.load_wandb_credential()
        marker = json.dumps({'report_id': key, 'evidence_hash': report['evidence_hash'],
                             'markdown_hash': digest(report['markdown'])}, sort_keys=True)
        remote = wr.Report(entity=self.entity, project=self.project, title=f'Research evidence · {key}',
                           description='Frozen validation research evidence. No benchmark superiority certification.',
                           blocks=[wr.MarkdownBlock(text=report['markdown']),
                                   wr.MarkdownBlock(text='Publication identity\n\n```json\n' + marker + '\n```')])
        remote.save()
        return remote.url.replace('\\', '/')

    def read(self, url):
        import wandb_workspaces.reports.v2 as wr
        remote = wr.Report.from_url(url)
        for block in remote.blocks:
            text = getattr(block, 'text', '')
            if text.startswith('Publication identity\n\n```json\n'):
                identity = json.loads(text.split('```json\n', 1)[1].split('\n```', 1)[0])
                if not remote.blocks or digest(getattr(remote.blocks[0], 'text', '')) != identity.get('markdown_hash'):
                    raise ValueError('Published report content differs from frozen Markdown')
                return identity
        raise ValueError('Published report has no evidence identity block')
