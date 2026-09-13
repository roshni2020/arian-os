"""Read-only evidence audit; no training, ARIA invocation, or cloud writes."""
import json
import math
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from sklearn.metrics import average_precision_score
from wildfire_researcher import config, final_eval, protocol

db = sqlite3.connect(f'file:{config.DB_PATH.as_posix()}?mode=ro', uri=True)
db.row_factory = sqlite3.Row
report = {'sessions': [], 'guard_checks': {}}
sessions = ['wf-20260913-live1', 'wf-20260913-104003-2c71']
for sid in sessions:
    s = dict(db.execute('select * from sessions where id=?', (sid,)).fetchone())
    rows = [dict(r) for r in db.execute('select * from experiments where session_id=? order by iteration', (sid,))]
    replay = json.loads((config.ARTIFACTS_DIR / sid / 'replay.json').read_text())
    final = json.loads(s['final_evaluation_json'])
    pred_checks = []
    for row in rows:
        result = json.loads(row['result_json'])
        p = np.load(result['predictions_path'], allow_pickle=True)
        ap = float(average_precision_score(p['y_true'], p['y_score']))
        assert math.isfinite(ap) and abs(ap-row['score']) < 1e-12
        saved = next(e for e in replay['experiments'] if e['id'] == row['id'])
        assert saved['result'] == result
        assert saved['experiment'] == json.loads(row['experiment_json'])
        assert saved['score'] == row['score'] and saved['decision'] == row['decision']
        pred_checks.append({'id': row['id'], 'auprc_recomputed': ap, 'controller': row['controller']})
    replay_final_matches = replay['session']['final_evaluation'] == final
    values = [r['test_auprc'] for r in final['per_seed']]
    assert abs(float(np.mean(values))-final['mean_test_auprc']) < 1e-12
    assert abs(float(np.std(values, ddof=1))-final['std_test_auprc']) < 1e-12
    msgs = [dict(m) for m in db.execute('select * from aria_messages where session_id=? and direction=?', (sid, 'inbound'))]
    test_mentions = []
    for m in msgs:
        # Candidate mentions for manual review, not a proof of hidden context isolation.
        payload = m['payload_json']
        if any(str(v)[:6] in payload for v in [0.5413, 0.5437, 0.5285]):
            test_mentions.append(m['id'])
    events = [dict(e) for e in db.execute("select ts,message from events where session_id=? and (message like '%Official test%' or kind='session_created' or kind='final_decision') order by id", (sid,))]
    report['sessions'].append({'id':sid, 'created_at':s['created_at'], 'final_recommended':json.loads(s['final_decision_json'])['recommended_final_experiment_id'],
      'evaluated':final['experiment_id'], 'mean_test_auprc':final['mean_test_auprc'], 'sample_std':final['std_test_auprc'],
      'seed_count':len(values), 'replay_experiments_match':True, 'replay_final_matches':replay_final_matches,
      'replay_final_present':replay['session']['final_evaluation'] is not None, 'validation_predictions':pred_checks,
      'inbound_messages':len(msgs), 'candidate_test_score_mentions':test_mentions, 'events':events})

# Probe guard behavior using a stub; never access test arrays or alter the live DB.
class ReachedTestLoader(Exception): pass
class FakeStore:
    def get_session(self, sid):
        return {'status':'training', 'limit_train_samples':None, 'final_decision':None,
                'final_evaluation':{'already':'evaluated'}, 'aria_mode':'fallback'}
    def get_experiment(self, sid, eid):
        return {'status':'claimed','experiment':{'feature_protocol':'all','weather_days':5}}
    def set_status(self, *args): pass
with patch.object(protocol, 'load_sealed_test_split', side_effect=ReachedTestLoader):
    try:
        final_eval.prepare_freeze(FakeStore(), 'fake', 'unfrozen', seeds=[7])
    except ValueError:
        report['guard_checks']['custom_seed_rejected_before_test_access'] = True
with patch.object(protocol, 'repo_commit', return_value=None):
    report['guard_checks']['unknown_repository_revision_comparable'] = final_eval.comparable({'feature_protocol':'all'}, {'limit_train_samples':None})

config.load_wandb_credential()
import wandb
api = wandb.Api()
for sr in report['sessions']:
    sid = sr['id']
    local = json.loads((config.ARTIFACTS_DIR / sid / 'final_evaluation.json').read_text())
    remote = api.run(f"{config.WANDB_ENTITY}/{config.WANDB_PROJECT}/{local['wandb_run_url'].rsplit('/',1)[-1]}")
    assert remote.state == 'finished'
    assert math.isfinite(remote.summary['mean_test_auprc'])
    assert abs(remote.summary['mean_test_auprc']-local['mean_test_auprc']) < 1e-12
    a = api.artifact(f'{config.WANDB_ENTITY}/{config.WANDB_PROJECT}/{sid}-final-evaluation:v0')
    downloaded = Path(a.download(root=str(config.ARTIFACTS_DIR / 'audit' / sid)))
    assert json.loads((downloaded/'final_evaluation.json').read_text()) == local
    sr['remote_final_matches'] = {'run':remote.id, 'artifact_digest':a.digest}
    sr['proposal_provenance'] = []
    for m in db.execute('select artifact_ref,artifact_digest from aria_messages where session_id=? and direction=? and accepted=1', (sid,'inbound')):
        a = api.artifact(m['artifact_ref'])
        assert a.digest == m['artifact_digest']
        sr['proposal_provenance'].append({'ref':m['artifact_ref'],'version':a.version,'metadata':a.metadata})
out = config.ARTIFACTS_DIR/'audit'/'handoff_audit_after_fixes.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
