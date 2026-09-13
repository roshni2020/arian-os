"""Immutable allowlisted validation evidence; never include test results or model narratives."""
import hashlib
import json
from datetime import datetime, timezone

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def evidence_protocol(session=None, project=None):
    """Return retrieval identity from a session or a server-verified executable project."""
    from .verification import protocol_identity, digest as protocol_digest
    if session is not None:
        identity = protocol_identity(session)
    elif project and (project.get('compatibility') or {}).get('executable') is True:
        from ..protocol import provenance
        identity = protocol_identity({'protocol': provenance(), 'limit_train_samples': None})
    else:
        return {'protocol': {}, 'protocol_fingerprint': None}
    return {'protocol': identity, 'protocol_fingerprint': protocol_digest(identity)}

def normalize_exclusions(values):
    if values is None: return []
    if not isinstance(values, list) or len(values) > 100 or any(
        not isinstance(value, str) or not 1 <= len(value) <= 200 for value in values):
        raise ValueError('excluded_finding_ids must contain at most 100 bounded string identities')
    return sorted(set(values))

def build_snapshot(store, session_id, experiment_ids, subgroup=None, project=None, findings=None, excluded_finding_ids=None):
    exclusions = normalize_exclusions(excluded_finding_ids)
    if subgroup is not None and (not isinstance(subgroup, dict) or set(subgroup) != {'dimension','group'} or
        any(not isinstance(subgroup[key], str) or not 1 <= len(subgroup[key]) <= 200 for key in ('dimension','group'))):
        raise ValueError('Subgroup requires exact nonempty dimension and group keys')
    subgroup_matches = 0
    session = store.get_session(session_id) if session_id else None
    if not session and not project: raise ValueError("Session or saved project required")
    if len(experiment_ids) > 8 or len(set(experiment_ids)) != len(experiment_ids):
        raise ValueError("Select at most eight distinct experiments")
    evidence = []
    def add(eid, path, value):
        evidence.append({"id": "ev-" + digest([session_id, eid, path])[:20], "session_id": session_id,
                         "experiment_id": eid, "path": path, "value": value})
    for eid in experiment_ids:
        if not session: raise ValueError("Experiments require a session")
        run = store.get_experiment(session_id, eid)
        result = run.get("result") or {}
        if result.get("split") not in ("validation", "val", "val (2019)"):
            raise ValueError("Only validation results may enter discovery evidence")
        if result.get('score_kind') not in ('VALIDATION_AUPRC','DEV_SCORE'):
            raise ValueError('Unknown validation score kind')
        add(eid, "updated_at", run.get("updated_at"))
        for key in ("model", "feature_protocol", "weather_days", "hyperparameters"):
            add(eid, "experiment." + key, (run.get("experiment") or {}).get(key))
        for key in ("score_kind", "split", "validation_auprc", "validation_auroc", "train_auprc",
                    "threshold_best_f1", "false_negative_count", "false_positive_count",
                    "val_positives", "val_size", "train_size", "n_features", "runtime_seconds", "seed"):
            if key in result: add(eid, "result." + key, result[key])
        for field, keys in {'confusion_matrix': ('tp','fp','tn','fn'),
                            'validation_metrics': ('precision','recall','f1','accuracy','auprc','auroc')}.items():
            for key in keys:
                if key in (result.get(field) or {}): add(eid, f'result.{field}.{key}', result[field][key])
        for dimension, rows in (result.get("error_breakdowns") or {}).items():
            if subgroup and dimension != subgroup.get("dimension"): continue
            for index, row in enumerate(rows):
                if subgroup and str(row.get("group")) != str(subgroup.get("group")): continue
                if subgroup: subgroup_matches += 1
                for key in ("group", "count", "positives", "false_negatives", "false_positives", "recall", "small_group"):
                    if key in row: add(eid, f"result.error_breakdowns.{dimension}.{index}.{key}", row[key])
    if subgroup and not subgroup_matches:
        raise ValueError('Selected subgroup dimension/group is absent from all selected runs; choose a recorded group')
    if project:
        for key in ("id", "name", "benchmark_id", "budget"):
            if key in project: add(None, "project." + key, project[key])
        spec = project.get('snapshot') or {}
        for key in ('task', 'task_type', 'dataset', 'dataset_identifier', 'dataset_id', 'dataset_revision',
                    'metric', 'metric_name', 'metric_direction', 'split', 'train_split', 'validation_split', 'executor'):
            value = spec.get(key)
            if isinstance(value, (str, int, float, bool)): add(None, 'project.snapshot.' + key, value)
    from ..experiments import capability_manifest
    capabilities = capability_manifest()
    scope = evidence_protocol(session, project)
    protocol, protocol_fingerprint = scope['protocol'], scope['protocol_fingerprint']
    for finding in (findings or [])[:8]:
        if finding.get('id') in exclusions or not protocol_fingerprint: continue
        if finding.get('test_exposed') or finding.get('protocol_fingerprint') != protocol_fingerprint: continue
        try: source = store.get_session(finding['session_id'])
        except KeyError: continue  # missing historical sources are never fabricated
        if source.get('final_evaluation') or source.get('aria_mode') != 'connected': continue
        try: source_run = store.get_experiment(finding['session_id'], finding['experiment_id'])
        except KeyError: continue
        if finding.get('source_revision') and finding['source_revision'] != source_run.get('updated_at'): continue
        with store.connect() as db:
            if db.execute('SELECT 1 FROM final_evaluation_freezes WHERE session_id=?', (finding['session_id'],)).fetchone(): continue
        for key in ('id','session_id','experiment_id','outcome','metrics','config','verification','protocol_fingerprint'):
            if key not in finding: continue
            path = 'findings.' + str(finding['id']) + '.' + key
            evidence.append({'id': 'ev-' + digest([finding['session_id'], finding['experiment_id'], path])[:20],
                             'session_id': finding['session_id'], 'experiment_id': finding['experiment_id'],
                             'path': path, 'value': finding[key]})
    body = {"schema_version": 1, "session_id": session_id,
            "session_revision": session.get("state_revision") if session else None,
            "experiment_ids": experiment_ids, "subgroup": subgroup,
            "excluded_finding_ids": exclusions,
            "project_id": project.get("id") if project else None,
            "project_snapshot_hash": digest(project['snapshot']) if project and 'snapshot' in project else None,
            "test_exposed": bool(session and session.get("final_evaluation")), "evidence": evidence,
            'capabilities': capabilities, 'protocol': protocol, 'protocol_fingerprint': protocol_fingerprint}
    return {**body, "id": "snapshot-" + digest(body)[:24], "hash": digest(body),
            "created_at": datetime.now(timezone.utc).isoformat()}
