"""Durable asynchronous requests with explicit capability and side-effect boundaries."""
import json
import uuid
from datetime import datetime, timezone
from .contracts import KINDS, validate_response
from .evidence import build_snapshot, canonical, digest, normalize_exclusions
from .storage import AssistantStore

def now(): return datetime.now(timezone.utc).isoformat()

class AssistantService:
    def __init__(self, store, path=None, transport=None):
        self.store = store
        self.db = AssistantStore(path or store.path.with_name("assistant.sqlite3"))
        self.transport = transport

    def capability(self):
        with self.db.connect() as db:
            row = db.execute("SELECT value FROM assistant_settings WHERE key='transport_proof'").fetchone()
        proof = json.loads(row[0]) if row else None
        identity = self.transport.identity() if self.transport and hasattr(self.transport, 'identity') else None
        verified = bool(proof and self.transport and proof.get('identity') == identity)
        return {"verified": verified, "manual_import_available": True,
                "reason": "Dedicated ARIA transport verified" if verified else
                "Dedicated ARIA Automation has not been verified; requests can be saved and responses imported.",
                "proof": json.loads(row[0]) if row else None}

    def create(self, kind, session_id=None, experiment_ids=None, question="", idempotency_key=None, subgroup=None, project=None, findings=None, excluded_finding_ids=None):
        experiment_ids = experiment_ids or []
        exclusions = normalize_exclusions(excluded_finding_ids)
        if kind not in KINDS: raise ValueError("Unknown request kind")
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 8000: raise ValueError("Question required (maximum 8000 characters)")
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 200: raise ValueError("Idempotency key required")
        # The idempotency key identifies user input, not a fresh retrieval/catalog result.
        # Retries retain the first immutable snapshot even if matching findings have advanced.
        fingerprint = digest([kind, session_id, experiment_ids, question, subgroup,
                              project.get('id') if project else None, exclusions])
        with self.db.connect() as db:
            existing = db.execute("SELECT * FROM assistant_requests WHERE idem=?", (idempotency_key,)).fetchone()
            if existing:
                saved = json.loads(existing['body'])
                saved_input = digest([saved['kind'], saved['session_id'], saved['snapshot']['experiment_ids'],
                                      saved['question'], saved['snapshot'].get('subgroup'), saved.get('project_id'),
                                      saved['snapshot'].get('excluded_finding_ids', [])])
                if saved_input != fingerprint: raise ValueError("Idempotency key reused with different input")
                return saved
            snapshot = build_snapshot(self.store, session_id, experiment_ids, subgroup, project, findings, exclusions)
            request = {"id": "aria-assistant-" + uuid.uuid4().hex, "kind": kind, "session_id": session_id,
                       "project_id": project.get("id") if project else None, "question": question,
                       "snapshot": snapshot, "status": "queued", "created_at": now(), "updated_at": now(),
                       "attempt": 0, "response": None, "provenance": None, "error": None}
            db.execute("INSERT INTO assistant_requests VALUES (?,?,?,?,?,?)",
                       (request['id'], idempotency_key, fingerprint, session_id, 'queued', canonical(request)))
            db.execute("INSERT INTO assistant_outbox(request_id,state) VALUES (?,'pending')", (request['id'],))
            return request

    def get(self, request_id):
        with self.db.connect() as db:
            row = db.execute("SELECT body FROM assistant_requests WHERE id=?", (request_id,)).fetchone()
        if not row: raise KeyError(request_id)
        return json.loads(row[0])

    def list(self, session_id=None):
        with self.db.connect() as db:
            rows = db.execute("SELECT body FROM assistant_requests WHERE session_id IS ? ORDER BY rowid DESC LIMIT 100", (session_id,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def pending(self):
        """Read-only recovery inventory across sessions. Does not claim or dispatch."""
        with self.db.connect() as db:
            rows = db.execute("SELECT body FROM assistant_requests WHERE status IN "
                              "('queued','dispatched','waiting','failed') ORDER BY rowid LIMIT 500").fetchall()
        records = [json.loads(row[0]) for row in rows]
        return [record for record in records if record.get('error') != 'response_invalid']

    def recover_once(self):
        """One explicit worker pass. Ambiguous records reconcile; cancelled records stay closed."""
        if not self.capability()['verified']: raise ValueError('Verified ARIA transport required for recovery')
        results = []
        for original in self.pending():
            request_id = original['id']
            try:
                request = self.get(request_id)
                if request['status'] in {'dispatched','failed','timed_out'}:
                    request = self.reconcile(request_id)
                    if request['status'] == 'failed' and request.get('error') == 'confirmed_not_dispatched':
                        request = self.retry(request_id)
                if request['status'] == 'queued': request = self.dispatch(request_id)
                if request['status'] == 'waiting':
                    request = self.poll(request_id)
                    if request['status'] == 'waiting':
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                            request.get('dispatched_at') or request['updated_at'])).total_seconds()
                        if age >= 900: request = self.timeout(request_id)
                results.append({'id':request_id, 'status':request['status']})
            except Exception as exc:
                # Persisted record is unchanged on a failed reconciliation; keep worker alive.
                results.append({'id': request_id, 'status': self.get(request_id)['status'],
                                'error_type': type(exc).__name__})
        return results

    def _update(self, request_id, allowed, **fields):
        with self.db.connect() as db:
            row = db.execute("SELECT body FROM assistant_requests WHERE id=?", (request_id,)).fetchone()
            if not row: raise KeyError(request_id)
            request = json.loads(row[0])
            if request['status'] not in allowed: raise ValueError("Request transition is no longer available")
            request.update(fields, updated_at=now())
            db.execute("UPDATE assistant_requests SET status=?,body=? WHERE id=?", (request['status'], canonical(request), request_id))
            db.execute("UPDATE assistant_outbox SET state=? WHERE request_id=?",
                       ({'queued':'pending','waiting':'sent','succeeded':'consumed','cancelled':'cancelled',
                         'failed':'reconcile','timed_out':'reconcile'}.get(request['status'],'claimed'), request_id))
            return request

    def cancel(self, request_id):
        request = self.get(request_id)
        if request['status'] == 'cancelled': return request
        return self._update(request_id, {'queued','dispatched','waiting','failed','timed_out'}, status='cancelled')

    def retry(self, request_id):
        request = self.get(request_id)
        if request['attempt'] >= 3: raise ValueError("Retry limit reached")
        if request.get('error') == 'response_invalid':
            raise ValueError('ARIA response was rejected; create a fresh request with a new evidence snapshot')
        # Ambiguous external dispatch cannot be retried until a human reconciles its deterministic run.
        if request.get('error') == 'dispatch_ambiguous': raise ValueError("Reconcile existing W&B run before retrying")
        return self._update(request_id, {'failed','timed_out'}, status='queued', error=None)

    def dispatch(self, request_id, probe=False):
        if not self.transport: raise ValueError("Transport not configured")
        if not probe and not self.capability()['verified']: raise ValueError("ARIA transport is not verified")
        with self.db.connect() as db:
            row = db.execute("SELECT body FROM assistant_requests WHERE id=?", (request_id,)).fetchone()
            if not row: raise KeyError(request_id)
            request = json.loads(row[0])
            if request['status'] != 'queued': raise ValueError("Request already claimed")
            if request['attempt'] >= 3: raise ValueError('Retry limit reached')
            request.update(status='dispatched', attempt=request['attempt'] + 1, updated_at=now(), dispatched_at=now())
            db.execute("UPDATE assistant_requests SET status='dispatched',body=? WHERE id=?", (canonical(request), request_id))
            db.execute("UPDATE assistant_outbox SET state='claimed',lease=?,attempts=attempts+1 WHERE request_id=?", (now(),request_id))
        try: provenance = self.transport.dispatch(request)
        except Exception:
            try: self._update(request_id, {'dispatched'}, status='failed', error='dispatch_ambiguous')
            except ValueError: pass  # cancellation remains authoritative
            raise
        try: return self._update(request_id, {'dispatched'}, status='waiting', provenance=provenance)
        except ValueError: return self.get(request_id)  # cancellation won the race

    def import_response(self, request_id, payload, provenance=None):
        request = self.get(request_id)
        validated = validate_response(payload, request)
        provenance = {**(provenance or {}), 'transport': 'manual-import', 'aria_verified': False,
                      'response_hash': digest(payload)}
        return self._complete(request, validated, provenance)

    def _complete(self, request, payload, provenance):
        if request['status'] == 'succeeded':
            if request['response'] == payload: return request
            raise ValueError("Response is immutable")
        return self._update(request['id'], {'queued','dispatched','waiting','failed','timed_out'},
                            status='succeeded', response=payload, provenance=provenance, error=None)

    def poll(self, request_id):
        request = self.get(request_id)
        if request['status'] not in {'waiting','dispatched','failed'}: return request
        if not self.transport: raise ValueError("Transport not configured")
        if request.get('error') == 'response_invalid': return request
        try:
            result = self.transport.poll(request)
        except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
            return self._update(request_id, {'waiting','dispatched','failed'}, status='failed',
                                error='response_invalid', error_detail='Malformed ARIA response: ' + str(exc)[:500])
        if result is None: return request
        payload, provenance = result
        try:
            validate_response(payload, request)
        except (ValueError, KeyError, TypeError) as exc:
            return self._update(request_id, {'waiting','dispatched','failed'}, status='failed',
                                error='response_invalid', error_detail='ARIA response rejected: ' + str(exc)[:500],
                                provenance=provenance)
        return self._complete(request, payload, provenance)

    def reconcile(self, request_id):
        """Read remote deterministic run identity before permitting another dispatch."""
        request = self.get(request_id)
        if request.get('error') == 'response_invalid':
            raise ValueError('Rejected response is terminal; create a fresh request')
        if request['status'] not in {'failed','dispatched','timed_out'}: return request
        if not self.transport: raise ValueError('Transport not configured')
        found = self.transport.reconcile(request)
        if found:
            return self._update(request_id, {'failed','dispatched','timed_out'}, status='waiting',
                                provenance=found, error=None)
        return self._update(request_id, {'failed','dispatched','timed_out'}, status='failed', error='confirmed_not_dispatched')

    def timeout(self, request_id):
        request = self.get(request_id)
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(
            request.get('dispatched_at') or request['updated_at'])).total_seconds()
        if age < 900: raise ValueError('Request timeout has not elapsed')
        return self._update(request_id, {'waiting','dispatched'}, status='timed_out', error='dispatch_ambiguous')

    def verify_transport(self, request_id):
        request = self.get(request_id)
        proof = request.get('provenance') or {}
        if request['status'] != 'succeeded' or proof.get('transport') != 'wandb-aria' or not proof.get('artifact_digest'):
            raise ValueError("A real validated ARIA artifact response is required")
        with self.db.connect() as db:
            db.execute("INSERT OR REPLACE INTO assistant_settings VALUES ('transport_proof',?)",
                       (canonical({'request_id':request_id, **proof,
                                   'identity': self.transport.identity() if hasattr(self.transport, 'identity') else None}),))
        return self.capability()
