"""Structured discovery findings. Never ingest free-form post-test narratives."""
from .verification import Records, VerificationService, digest, eligible, protocol_identity
from ..state import now


class MemoryService(Records):
    def __init__(self, store):
        super().__init__(store, 'assistant_research_findings')

    def refresh(self, session_id):
        session = self.store.get_session(session_id)
        fingerprint = digest(protocol_identity(session))
        # Fail closed: a post-test session cannot become future discovery context.
        with self.store.connect() as c:
            exposed = c.execute('SELECT 1 FROM final_evaluation_freezes WHERE session_id=?', (session_id,)).fetchone()
        if exposed or session.get('final_evaluation') or session.get('aria_mode') != 'connected':
            return []
        findings = []
        studies = VerificationService(self.store).list(session_id)
        for exp in self.store.experiments(session_id):
            result = exp.get('result')
            if not eligible(result):
                continue
            metrics = {k: result.get(k) for k in ('validation_auprc', 'validation_auroc', 'train_auprc', 'false_negative_count', 'false_positive_count', 'seed', 'train_size', 'val_size', 'score_kind', 'split')}
            body = {'session_id': session_id, 'experiment_id': exp['id'], 'protocol_fingerprint': fingerprint,
                    'config': exp['experiment'], 'metrics': metrics, 'outcome': exp.get('decision'),
                    'citation': f'{session_id}/{exp["id"]}', 'source_revision': exp.get('updated_at'),
                    'verification': [
                        {'id': study['id'], 'plan_hash': study['plan_hash'],
                         'baseline_id': study['plan']['baseline_id'], 'candidate_id': study['plan']['candidate_id'],
                         'summary': study['summary']}
                        for study in studies if study['status'] == 'complete'
                        and study['plan']['protocol_fingerprint'] == fingerprint
                        and any(study['plan'][arm + '_id'] == exp['id']
                                and study['plan']['configs'][arm] == exp['experiment']
                                for arm in ('baseline', 'candidate'))][:10],
                    'limitations': ['Single discovery experiment; no causal or test superiority claim.',
                                    'Free-form reasoning is excluded to prevent post-test narrative reuse.']}
            h = digest(body)
            findings.append(self.insert({**body, 'id': 'finding-' + h[:24], 'created_at': now(), 'input_hash': h}, h))
        return findings

    def search(self, protocol_fingerprint, query='', limit=20):
        if not protocol_fingerprint:
            raise ValueError('A compatible protocol fingerprint is required')
        limit = min(50, max(1, int(limit)))
        # Fetch latest versions only and re-check exposure at retrieval time.
        with self.db() as c:
            rows = c.execute(f'SELECT body FROM {self.table} ORDER BY rowid DESC').fetchall()
        import json
        found, seen = [], set()
        candidates = [json.loads(row['body']) for row in rows]
        # Stable sorting retains newest indexed version for ties while prioritizing
        # actual source recency over the order sessions happened to be indexed.
        candidates.sort(key=lambda item: str(item.get('source_revision') or ''), reverse=True)
        for item in candidates:
            key = (item['session_id'], item['experiment_id'])
            if key in seen:
                continue
            seen.add(key)
            if item['protocol_fingerprint'] != protocol_fingerprint:
                continue
            try:
                session = self.store.get_session(item['session_id'])
                current = self.store.get_experiment(item['session_id'], item['experiment_id'])
            except KeyError:
                continue
            if digest(protocol_identity(session)) != protocol_fingerprint or current.get('experiment') != item['config']:
                continue
            with self.store.connect() as c:
                exposed = c.execute('SELECT 1 FROM final_evaluation_freezes WHERE session_id=?', (item['session_id'],)).fetchone()
            if exposed or session.get('final_evaluation') or session.get('aria_mode') != 'connected':
                continue
            if not eligible(current.get('result')) or current.get('updated_at') != item['source_revision']:
                continue
            if any(current['result'].get(k) != v for k, v in item['metrics'].items()) or current.get('decision') != item['outcome']:
                continue
            verified = []
            for reference in item.get('verification', []):
                try:
                    study = VerificationService(self.store).get(reference['id'])
                except KeyError:
                    continue
                if (study['status'] == 'complete' and study['plan_hash'] == reference['plan_hash']
                        and study['summary'] == reference['summary']):
                    verified.append(reference)
            item['verification'] = verified
            # Match only selected safe structured fields, not source logs or narratives.
            if query and query.casefold() not in json.dumps({'config': item['config'], 'outcome': item['outcome'], 'citation': item['citation']}).casefold():
                continue
            found.append(item)
            if len(found) >= limit:
                break
        return found
