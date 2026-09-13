"""Frozen, validation-only paired-seed studies, separate from discovery budgets."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from ..state import now


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def protocol_identity(session):
    p = session.get('protocol') or {}
    keys = ('repo', 'pinned_commit', 'dataset', 'dataset_revision', 'task', 'representation',
            'split_years', 'label_rule', 'prediction_time', 'metric')
    return {**{k: p.get(k) for k in keys}, 'limit_train_samples': session.get('limit_train_samples')}


def eligible(result):
    return bool(result and result.get('split') in ('val', 'val (2019)') and
                result.get('score_kind') in ('VALIDATION_AUPRC', 'DEV_SCORE'))


class Records:
    def __init__(self, store, table):
        self.store = store
        self.path = Path(store.path).parent / 'assistant.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.table = table
        with self.db() as c:
            c.execute(f'CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, idem TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(session_id,idem))')

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def get(self, record_id):
        with self.db() as c:
            row = c.execute(f'SELECT body FROM {self.table} WHERE id=?', (record_id,)).fetchone()
        if not row:
            raise KeyError(record_id)
        return json.loads(row['body'])

    def list(self, session_id):
        with self.db() as c:
            rows = c.execute(f'SELECT body FROM {self.table} WHERE session_id=? ORDER BY rowid DESC', (session_id,)).fetchall()
        return [json.loads(r['body']) for r in rows]

    def save(self, value, c):
        c.execute(f'UPDATE {self.table} SET body=? WHERE id=?', (json.dumps(value, allow_nan=False), value['id']))

    def insert(self, value, idem):
        if not isinstance(idem, str) or not 1 <= len(idem) <= 200:
            raise ValueError('A bounded idempotency key is required')
        with self.db() as c:
            row = c.execute(f'SELECT body FROM {self.table} WHERE session_id=? AND idem=?', (value['session_id'], idem)).fetchone()
            if row:
                previous = json.loads(row['body'])
                if previous.get('input_hash') != value.get('input_hash'):
                    raise ValueError('Idempotency key already used for different inputs')
                return previous
            c.execute(f'INSERT INTO {self.table} VALUES (?,?,?,?)', (value['id'], value['session_id'], idem, json.dumps(value, allow_nan=False)))
        return value


class VerificationService(Records):
    def __init__(self, store):
        super().__init__(store, 'assistant_verification_studies')

    def create(self, session_id, baseline_id, candidate_id, seeds, idempotency_key, max_runs=20):
        session = self.store.get_session(session_id)
        if session.get('aria_mode') == 'replay':
            raise ValueError('Replay cannot create verification studies')
        if baseline_id == candidate_id:
            raise ValueError('Select two different experiments')
        if not isinstance(seeds, list) or not 2 <= len(seeds) <= 10 or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds) or len(set(seeds)) != len(seeds):
            raise ValueError('Provide 2–10 unique integer seeds')
        if type(max_runs) is not int or not 4 <= max_runs <= 20 or 2 * len(seeds) > max_runs:
            raise ValueError('Paired runs exceed the explicit 4–20 run budget')
        records = [self.store.get_experiment(session_id, x) for x in (baseline_id, candidate_id)]
        if any(not eligible(r.get('result')) for r in records):
            raise ValueError('Only recorded validation experiments can be verified')
        a, b = [r['result'] for r in records]
        if any(a.get(k) is None or a.get(k) != b.get(k) for k in ('split', 'score_kind', 'train_size', 'val_size')):
            raise ValueError('Experiments have incompatible evaluation conditions')
        plan = {'baseline_id': baseline_id, 'candidate_id': candidate_id, 'seeds': seeds,
                'configs': dict(zip(('baseline', 'candidate'), [r['experiment'] for r in records])),
                'protocol': protocol_identity(session), 'protocol_fingerprint': digest(protocol_identity(session)),
                'max_runs': max_runs, 'split': 'val', 'score_kind': a['score_kind'],
                'train_size': a['train_size'], 'val_size': a['val_size'],
                'limit_train_samples': session.get('limit_train_samples')}
        rid = 'verify-' + uuid.uuid4().hex
        return self.insert({'id': rid, 'session_id': session_id, 'status': 'draft', 'plan': plan,
                            'input_hash': digest(plan), 'plan_hash': digest(plan), 'created_at': now(),
                            'updated_at': now(), 'cancel_requested': False,
                            'children': [{'id': f'{rid}-{arm}-{seed}', 'arm': arm, 'seed': seed, 'status': 'pending', 'result': None, 'error': None}
                                         for seed in seeds for arm in ('baseline', 'candidate')],
                            'summary': self.summarize([], len(seeds))}, idempotency_key)

    @staticmethod
    def summarize(children, expected_pairs=None):
        import statistics
        pairs = {}
        for child in children:
            if child['status'] == 'complete':
                pairs.setdefault(child['seed'], {})[child['arm']] = child['result']['validation_auprc']
        deltas = [{'seed': seed, 'baseline_auprc': pair['baseline'], 'candidate_auprc': pair['candidate'],
                   'delta': pair['candidate'] - pair['baseline']} for seed, pair in sorted(pairs.items()) if len(pair) == 2]
        values = [p['delta'] for p in deltas]
        expected_pairs = expected_pairs if expected_pairs is not None else len({c['seed'] for c in children})
        return {'paired_deltas': deltas, 'mean_delta': sum(values) / len(values) if values else None,
                'std_delta': statistics.stdev(values) if len(values) > 1 else None,
                'min_delta': min(values) if values else None, 'max_delta': max(values) if values else None,
                'expected_pairs': expected_pairs, 'incomplete': len(values) < expected_pairs,
                'variability_label': 'Sample standard deviation across paired seed deltas; not a confidence interval.',
                'complete_pairs': len(values), 'claim_eligible': False,
                'limitations': ['Validation-only repeated seeds; this is not an official test result.',
                                'Seed variation does not quantify dataset sampling uncertainty or remove adaptive validation bias.']}

    def cancel(self, record_id):
        with self.db() as c:
            row = c.execute(f'SELECT body FROM {self.table} WHERE id=?', (record_id,)).fetchone()
            if not row:
                raise KeyError(record_id)
            value = json.loads(row['body'])
            if value['status'] != 'complete':
                value.update(cancel_requested=True, status='cancelled', updated_at=now())
                self.save(value, c)
        return value

    def run(self, record_id, executor=None):
        try:
            return self._run(record_id, executor)
        except Exception as exc:
            with self.db() as c:
                row = c.execute(f'SELECT body FROM {self.table} WHERE id=?', (record_id,)).fetchone()
                if row:
                    value = json.loads(row['body'])
                    if value['status'] not in ('complete', 'cancelled', 'running'):
                        value.update(status='failed', error=str(exc)[:1000], updated_at=now())
                        self.save(value, c)
            raise

    def _run(self, record_id, executor=None):
        from ..execution import worker_lease, bounded
        from ..runner import run_experiment
        from .. import config
        # The global OS lease also excludes discovery and final-evaluation workers.
        with worker_lease():
            value = self.get(record_id)
            if value['status'] == 'complete' or value['cancel_requested']:
                return value
            if digest(value['plan']) != value['plan_hash']:
                raise ValueError('Frozen verification plan changed')
            if digest(protocol_identity(self.store.get_session(value['session_id']))) != value['plan']['protocol_fingerprint']:
                raise ValueError('Session protocol changed since verification was frozen')
            for index in range(len(value['children'])):
                with self.db() as c:
                    value = json.loads(c.execute(f'SELECT body FROM {self.table} WHERE id=?', (record_id,)).fetchone()['body'])
                    if value['cancel_requested']:
                        return value
                    child = value['children'][index]
                    if child['status'] == 'complete':
                        continue
                    child.update(status='running', error=None)
                    value.update(status='running', error=None, updated_at=now())
                    self.save(value, c)
                try:
                    kwargs = {'experiment': value['plan']['configs'][child['arm']], 'seed': child['seed'],
                              'out_dir': config.ARTIFACTS_DIR / 'verification' / child['id'],
                              'limit_train_samples': value['plan']['limit_train_samples']}
                    result = executor(**kwargs) if executor else bounded(run_experiment, **kwargs, should_cancel=lambda: self.get(record_id)['cancel_requested'])
                    if not eligible(result) or result.get('seed') != child['seed'] or any(result.get(k) != value['plan'][k] for k in ('score_kind', 'train_size', 'val_size')):
                        raise ValueError('Child result does not match frozen validation conditions')
                    score = result.get('validation_auprc')
                    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                        raise ValueError('Invalid validation average precision')
                    result = {k: result.get(k) for k in ('validation_auprc', 'validation_auroc', 'seed', 'split', 'score_kind', 'train_size', 'val_size', 'runtime_seconds', 'predictions_path', 'model_bundle_path')}
                    error = None
                except Exception as exc:
                    result, error = None, str(exc)[:1000]
                with self.db() as c:
                    value = json.loads(c.execute(f'SELECT body FROM {self.table} WHERE id=?', (record_id,)).fetchone()['body'])
                    value['children'][index].update(status='complete' if result else 'failed', result=result, error=error)
                    value['summary'] = self.summarize(value['children'])
                    value.update(status='cancelled' if value['cancel_requested'] else ('failed' if error else 'running'), updated_at=now())
                    if all(r['status'] == 'complete' for r in value['children']) and not value['cancel_requested']:
                        value['status'] = 'complete'
                    self.save(value, c)
                if error or value['cancel_requested']:
                    return value
            return value
