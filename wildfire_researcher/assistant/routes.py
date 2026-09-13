"""Additive assistant workflows. GETs observe; explicit POSTs dispatch or execute."""
from __future__ import annotations
import threading
import logging
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from .. import config, protocol

router = APIRouter(prefix='/api/assistant', tags=['assistant'])
_jobs = {}
_jobs_lock = threading.RLock()

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Scope(Input):
    session_id: str = Field(min_length=1, max_length=200)

class RequestInput(Input):
    kind: Literal['ask','error_proposal','study_plan','report']
    session_id: str | None = Field(default=None, max_length=200)
    project_id: str | None = Field(default=None, max_length=200)
    experiment_ids: list[str] = Field(default_factory=list, max_length=8)
    question: str = Field(min_length=1,max_length=8000)
    group: dict[str,str] | None = None
    excluded_finding_ids: list[str] = Field(default_factory=list,max_length=100)
    idempotency_key: str = Field(min_length=1,max_length=200)

class Version(Input):
    version_hash: str = Field(min_length=1,max_length=128)
    idempotency_key: str | None = None

class VerificationInput(Scope):
    baseline_id: str
    candidate_id: str
    seeds: list[StrictInt] = Field(min_length=2,max_length=10)
    max_runs: StrictInt = Field(default=20,ge=4,le=20)
    idempotency_key: str = Field(min_length=1,max_length=200)

class PlanHash(Input):
    plan_hash: str

class ReportInput(Scope):
    idempotency_key: str = Field(min_length=1,max_length=200)
    assistant_request_id: str | None = None

class PublishInput(Input):
    evidence_hash: str


def research_store():
    from ..api import store
    return store()


def assistant():
    from .requests import AssistantService
    from .transport import WandbAssistantTransport
    return AssistantService(research_store(), transport=WandbAssistantTransport(config.WANDB_ENTITY, config.WANDB_PROJECT))


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError:
        raise HTTPException(404, 'The requested research record does not exist') from None
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from None


def spawn(key, target):
    with _jobs_lock:
        if key in _jobs and _jobs[key].is_alive():
            return
        thread = threading.Thread(target=target, name=key, daemon=True)
        _jobs[key] = thread
        thread.start()


_recovery_stop = threading.Event()
_recovery_wake = threading.Event()


def process_request(identity=None):
    """One process-wide recovery loop; HTTP GETs never perform remote work."""
    while not _recovery_stop.is_set():
        try:
            svc = assistant()
            if svc.capability()['verified']:
                config.load_wandb_credential()
                svc.recover_once()
        except Exception as exc:
            logging.getLogger(__name__).warning('Assistant recovery deferred: %s', type(exc).__name__)
        _recovery_wake.wait(15)
        _recovery_wake.clear()


def wake_worker():
    _recovery_wake.set()
    spawn('assistant-recovery', process_request)


@router.on_event('startup')
def start_recovery():
    _recovery_stop.clear()
    wake_worker()


@router.on_event('shutdown')
def stop_recovery():
    _recovery_stop.set()
    _recovery_wake.set()


@router.get('/capabilities')
def capabilities():
    return {**assistant().capability(), 'verification': True, 'reports': True, 'study_plans': True}


@router.post('/requests')
def create_request(req: RequestInput):
    from ..benchmarks.routes import catalog
    project = call(catalog().get_project, req.project_id) if req.project_id else None
    if project and req.session_id and project.get('session_id') != req.session_id:
        raise HTTPException(409, 'Project and session scopes do not match')
    svc = assistant()
    from .memory import MemoryService
    from .evidence import evidence_protocol
    scope = call(research_store().get_session, req.session_id) if req.session_id else None
    fingerprint = evidence_protocol(scope, project)['protocol_fingerprint']
    related = []
    if fingerprint:
        memory = MemoryService(research_store())
        # This explicit POST refreshes durable findings before freezing its retrieval set.
        for source in research_store().list_sessions():
            memory.refresh(source['id'])
        related = [f for f in memory.search(fingerprint, limit=50) if f['id'] not in req.excluded_finding_ids][:8]
    item = call(svc.create, req.kind, session_id=req.session_id, experiment_ids=req.experiment_ids,
                question=req.question, idempotency_key=req.idempotency_key, subgroup=req.group, project=project, findings=related, excluded_finding_ids=req.excluded_finding_ids)
    if svc.capability()['verified'] and item['status'] == 'queued':
        wake_worker()
    return item


@router.get('/requests')
def requests(session_id: str | None = None, project_id: str | None = None):
    return {'items': [r for r in assistant().list(session_id) if not project_id or r.get('project_id') == project_id]}


@router.get('/requests/{identity}')
def request(identity: str):
    return call(assistant().get, identity)


@router.post('/requests/{identity}/cancel')
def cancel_request(identity: str):
    return call(assistant().cancel, identity)


@router.post('/requests/{identity}/retry')
def retry_request(identity: str):
    svc = assistant()
    item = call(svc.retry, identity)
    if svc.capability()['verified']:
        wake_worker()
    return item


@router.post('/requests/{identity}/draft')
def request_draft(identity: str):
    from .drafts import DraftService
    from ..benchmarks.routes import catalog
    item = call(assistant().get, identity)
    project = call(catalog().get_project, item['project_id']) if item.get('project_id') else None
    return call(DraftService(research_store()).create, item, project)


@router.post('/drafts/{identity}/start')
def start_draft(identity: str, req: Version):
    from .drafts import DraftService
    from .. import api
    from ..benchmarks.routes import catalog
    from ..execution import worker_lease
    svc = DraftService(research_store())
    with api._lock:
        draft = call(svc.get, identity)
        if req.version_hash != draft['version_hash']:
            raise HTTPException(409, 'Draft changed; review its current version')
        if draft['session']:
            saved = call(research_store().get_session, draft['session'])
            if saved['status'] != 'created':
                return {'draft':draft, 'session_id':saved['id'], 'journal_url':f"/?session={saved['id']}"}
        if any(w.is_alive() for w in api._workers.values()):
            raise HTTPException(409, 'Another local research worker is active')
        try:
            with worker_lease():
                pass
            config.load_wandb_credential()
        except Exception:
            raise HTTPException(409, 'Execution requires an idle worker and W&B credentials') from None
        if not protocol.canonical_ready() or protocol.repo_commit() != protocol.PINNED_COMMIT:
            raise HTTPException(409, 'The pinned dataset and executor are not ready')
        project = call(catalog().get_project, draft['project_id']) if draft['project_id'] else None
        draft = call(svc.prepare_start, identity, req.version_hash, entity=config.WANDB_ENTITY,
                     project=config.WANDB_PROJECT, current_project=project)
        if project and not project.get('session_id'):
            call(catalog().link_session, project['id'], draft['session'])
        api._start_worker(draft['session'], config.ARIA_WAIT_SECONDS)
        return {'draft':draft, 'session_id':draft['session'], 'journal_url':f"/?session={draft['session']}"}


@router.post('/verifications')
def create_verification(req: VerificationInput):
    from .verification import VerificationService
    return call(VerificationService(research_store()).create, req.session_id, req.baseline_id,
                req.candidate_id, req.seeds, req.idempotency_key, req.max_runs)


@router.get('/verifications')
def verifications(session_id: str):
    from .verification import VerificationService
    return {'items': call(VerificationService(research_store()).list, session_id)}


@router.get('/verifications/{identity}')
def verification(identity: str):
    from .verification import VerificationService
    return call(VerificationService(research_store()).get, identity)


@router.post('/verifications/{identity}/start')
def start_verification(identity: str, req: PlanHash):
    from .verification import VerificationService
    svc = VerificationService(research_store())
    item = call(svc.get, identity)
    if req.plan_hash != item['plan_hash']:
        raise HTTPException(409, 'Verification plan changed; review it before starting')
    if item['status'] in ('cancelled','complete'):
        return item
    from ..execution import worker_lease
    try:
        with worker_lease():
            pass
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None
    def run():
        try:
            svc.run(identity)
        except Exception:
            pass  # Service persists child-run failures; competing workers never train.
    spawn('verify-' + identity, run)
    return item


@router.post('/verifications/{identity}/cancel')
def cancel_verification(identity: str):
    from .verification import VerificationService
    return call(VerificationService(research_store()).cancel, identity)


@router.post('/findings/refresh')
def refresh_findings(req: Scope):
    from .memory import MemoryService
    call(research_store().get_session, req.session_id)
    svc = MemoryService(research_store())
    items = []
    for session in research_store().list_sessions():
        items.extend(svc.refresh(session['id']))
    return {'indexed': len(items)}


@router.get('/findings')
def findings(session_id: str, q: str = Query('',max_length=200)):
    from .memory import MemoryService
    from .verification import digest, protocol_identity
    session = call(research_store().get_session, session_id)
    return {'items': call(MemoryService(research_store()).search, digest(protocol_identity(session)), q)}


@router.post('/reports')
def create_report(req: ReportInput):
    from .reporting import ReportService
    narrative = call(assistant().get, req.assistant_request_id) if req.assistant_request_id else None
    return call(ReportService(research_store()).create, req.session_id, req.idempotency_key, aria_response=narrative)


@router.get('/reports')
def reports(session_id: str):
    from .reporting import ReportService
    return {'items': call(ReportService(research_store()).list, session_id)}


@router.get('/reports/{identity}')
def report(identity: str):
    from .reporting import ReportService
    return call(ReportService(research_store()).get, identity)


@router.get('/reports/{identity}/export')
def export_report(identity: str, format: Literal['markdown','json']='markdown'):
    from .reporting import ReportService
    content = call(ReportService(research_store()).export, identity, format)
    return Response(content, media_type='text/markdown' if format == 'markdown' else 'application/json',
        headers={'Content-Disposition': 'attachment; filename="research-report.' + ('md' if format == 'markdown' else 'json') + '"'})


@router.post('/reports/{identity}/publish')
def publish_report(identity: str, req: PublishInput):
    from .reporting import ReportService, WandbReportPublisher
    svc = ReportService(research_store())
    item = call(svc.get, identity)
    if req.evidence_hash != item['evidence_hash']:
        raise HTTPException(409, 'Report evidence changed; review the current report')
    call(config.load_wandb_credential)
    source = call(research_store().get_session, item['session_id'])
    return call(svc.publish, identity, WandbReportPublisher(source['wandb_entity'], source['wandb_project']))
