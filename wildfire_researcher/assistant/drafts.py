"""Reviewed ARIA drafts; accepting a draft creates a linked, fresh study."""
from __future__ import annotations
import hashlib
import json
import uuid
from datetime import datetime, timezone
from .. import protocol
from ..experiments import canonical_experiment, BASELINE_EXPERIMENT


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def approved_context(store, session_id):
    """Existing sessions need no migration or side effects to read their state."""
    with store.connect() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='assistant_reviewed_drafts'").fetchone()
        if not exists:
            return None
        row = db.execute('SELECT record_json FROM assistant_reviewed_drafts WHERE started_session_id=?', (session_id,)).fetchone()
    if not row:
        return None
    draft = json.loads(row[0])
    return {'draft_id': draft['id'], 'kind': draft['kind'], 'version_hash': draft['version_hash'],
            'origin_request_id': draft['request_id'], 'source_session_id': draft['session_id'],
            'plan': draft['content']}


class DraftService:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS assistant_reviewed_drafts (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, started_session_id TEXT UNIQUE,
                record_json TEXT NOT NULL)''')

    def get(self, identity):
        with self.store.connect() as db:
            row = db.execute('SELECT record_json FROM assistant_reviewed_drafts WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        return json.loads(row[0])

    def create(self, request, project=None):
        if request['status'] != 'succeeded' or not request.get('response'):
            raise ValueError('A validated ARIA response is required before creating a reviewed draft')
        if not (request.get('provenance') or {}).get('aria_verified'):
            raise ValueError('Executable drafts require a verified ARIA response; manual imports remain review-only')
        kind = request['kind']
        content = request['response'].get('draft')
        if kind not in ('error_proposal', 'study_plan') or not isinstance(content, dict):
            raise ValueError('This response does not contain an executable study draft')
        content = json.loads(json.dumps(content, allow_nan=False))
        if kind == 'error_proposal':
            content['experiment'] = canonical_experiment(content.get('experiment'))
            if content['experiment'] == canonical_experiment(BASELINE_EXPERIMENT):
                raise ValueError('The proposed configuration repeats the fixed baseline')
            budget = 1
        else:
            budget = content.get('experiment_budget')
            if type(budget) is not int or not 1 <= budget <= 50:
                raise ValueError('A study plan needs an integer experiment budget between 1 and 50')
        snapshot = request['snapshot']
        if snapshot.get('project_id'):
            if not project or project['id'] != snapshot['project_id'] or digest(project['snapshot']) != snapshot.get('project_snapshot_hash'):
                raise ValueError('Project changed since ARIA reviewed it; request a new plan')
        elif project:
            raise ValueError('The ARIA request was not scoped to this project')
        record = {'id': 'draft-' + uuid.uuid4().hex, 'request_id': request['id'], 'kind': kind,
                  'session_id': snapshot.get('session_id'), 'source_revision': snapshot.get('session_revision'),
                  'project_id': project.get('id') if project else None,
                  'project_hash': digest(project['snapshot']) if project else None,
                  'content': content, 'experiment_budget': budget, 'snapshot_hash': snapshot['hash'],
                  'protocol_fingerprint': snapshot.get('protocol_fingerprint'),
                  'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'draft', 'session': None}
        record['version_hash'] = digest(record)
        with self.store.connect() as db:
            old = db.execute('SELECT record_json FROM assistant_reviewed_drafts WHERE request_id=?', (request['id'],)).fetchone()
            if old:
                return json.loads(old[0])
            db.execute('INSERT INTO assistant_reviewed_drafts(id,request_id,record_json) VALUES (?,?,?)',
                       (record['id'], request['id'], json.dumps(record)))
        return record

    def prepare_start(self, identity, version_hash, *, entity, project, current_project=None):
        """Atomic local session creation; caller must separately start the worker."""
        with self.store.connect() as db:
            draft = self.get(identity)
            if draft['version_hash'] != version_hash:
                raise ValueError('Draft version changed; review the current draft before starting')
            if draft['session']:
                return draft
            if draft['project_id']:
                if not current_project or current_project['id'] != draft['project_id'] or digest(current_project['snapshot']) != draft['project_hash']:
                    raise ValueError('Project snapshot changed; request and review a new plan')
                if not current_project['compatibility']['executable']:
                    raise ValueError('The saved project does not have a supported executor')
            if draft['session_id']:
                source = self.store.get_session(draft['session_id'])
                if source['state_revision'] != draft['source_revision']:
                    raise ValueError('Source session changed; request a fresh ARIA draft')
                if source['status'] not in ('complete', 'cancelled', 'error'):
                    raise ValueError('The source study is active. Review this draft after it finishes; no competing proposal was inserted')
                from .verification import protocol_identity, digest as protocol_digest
                if draft.get('protocol_fingerprint') != protocol_digest(protocol_identity(source)):
                    raise ValueError('Source protocol changed; request a new ARIA draft')
                if protocol_identity(source) != protocol_identity({'protocol': protocol.provenance(), 'limit_train_samples': None}):
                    raise ValueError('Source protocol does not match the current supported executor')
                if source['aria_mode'] != 'connected' or source.get('limit_train_samples'):
                    raise ValueError('Only full-data connected research supports executable follow-up drafts')
            elif not current_project:
                raise ValueError('A supported project or source session is required')
            session = self.store.create_session(budget=draft['experiment_budget'], aria_mode='connected',
                research_seed=protocol.RESEARCH_SEED, fast_mode=False, limit_train_samples=None, entity=entity, project=project)
            draft['session'] = session['id']
            draft['status'] = 'approved'
            db.execute('UPDATE assistant_reviewed_drafts SET started_session_id=?,record_json=? WHERE id=?',
                       (session['id'], json.dumps(draft), identity))
            self.store.log_event(session['id'], 'approved_study_plan', 'Started from a reviewed ARIA draft',
                                 {'draft_id': identity, 'version_hash': version_hash, 'source_session_id': draft['session_id']})
        return draft
