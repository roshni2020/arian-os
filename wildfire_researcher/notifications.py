"""Persistent, deduplicated W&B alerts for research operations."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def alert_candidates(session, experiments, now=None, stall_seconds=900):
    if session['aria_mode'] != 'connected':
        return []
    now = now or datetime.now(timezone.utc)
    sid = session['id']; alerts = []
    for exp in experiments:
        if exp['status'] == 'failed':
            alerts.append((f'{sid}:failure:{exp["id"]}', 'ERROR', 'Experiment failed',
                           f'{sid}/{exp["id"]} failed. Inspect its W&B run and local event log.'))
    if len([e for e in experiments if e['controller']=='ARIA' and e['status']=='complete']) >= session['budget']:
        alerts.append((f'{sid}:budget', 'INFO', 'Research budget exhausted', f'{sid}: no experiment budget remains.'))
    if session.get('final_decision'):
        winner = session['final_decision'].get('recommended_final_experiment_id')
        alerts.append((f'{sid}:final-decision','INFO','ARIA final decision',f'{sid}: ARIA recommends {winner}.'))
    result = session.get('final_evaluation') or {}
    if result:
        # Old benchmark_beaten flags alone cannot certify a claim.
        eligible = result.get('claim_eligible') is True and result.get('benchmark_beaten') is True
        alerts.append((f'{sid}:evaluation','INFO','Certified benchmark improvement' if eligible else 'Test evaluation recorded',
                       f'{sid}: test AUPRC {result["mean_test_auprc"]:.4f}. '+
                       ('Claim gate passed.' if eligible else 'Descriptive result; benchmark certification unavailable.')))
    waiting = session['status'] in ('awaiting_aria_proposal','awaiting_final_decision')
    age = (now-datetime.fromisoformat(session['updated_at'])).total_seconds()
    if waiting and age >= stall_seconds:
        alerts.append((f'{sid}:stall:{session["state_revision"]}','WARN','ARIA session stalled',
                       f'{sid}: no state update for {int(age)} seconds at revision {session["state_revision"]}.'))
    if session['status']=='error':
        alerts.append((f'{sid}:error:{session["state_revision"]}','ERROR','Research session needs attention',
                       f'{sid}: session entered error state. Inspect the event log.'))
    return alerts


class AlertLedger:
    def __init__(self,path):
        self.path = Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS alerts (key TEXT PRIMARY KEY, level TEXT, title TEXT, text TEXT, state TEXT, error TEXT)')

    def connect(self):
        return sqlite3.connect(self.path,timeout=30)

    def enqueue(self,candidates,baseline=False):
        with self.connect() as db:
            for key,level,title,text in candidates:
                db.execute('INSERT OR IGNORE INTO alerts VALUES (?,?,?,?,?,NULL)',
                           (key,level,title,text,'historical' if baseline else 'pending'))

    def deliver(self,send):
        # Delivery is at least once if the process crashes after send and before commit.
        # A stable unique title and W&B wait_duration provide downstream deduplication too.
        with self.connect() as db:
            pending = db.execute("SELECT key,level,title,text FROM alerts WHERE state='pending'").fetchall()
        for key,level,title,text in pending:
            try:
                send(key,level,title,text)
            except Exception as exc:
                with self.connect() as db:
                    db.execute('UPDATE alerts SET error=? WHERE key=?',(type(exc).__name__,key))
            else:
                with self.connect() as db:
                    db.execute("UPDATE alerts SET state='sent',error=NULL WHERE key=?",(key,))


def run_monitor(once=False,test=False):
    import time
    import wandb
    from . import config
    from .state import Store
    config.load_wandb_credential()
    path=config.DATA_DIR/'operations-alerts.sqlite'
    first = not path.exists(); ledger=AlertLedger(path); store=Store()
    with wandb.init(entity=config.WANDB_ENTITY,project=config.WANDB_PROJECT,
                    name='operator-notifications',job_type='operations-monitor',
                    config={'purpose':'W&B operational alerts','benchmark_comparable':False}) as run:
        def send(key,level,title,text):
            run.alert(title=f'{title} [{key}]',text=text,level=level,wait_duration=86400)
            run.log({'notifications_sent':1})
        if test:
            ledger.enqueue([('installation-test-20260913','INFO','Wildfire notifications test',
                             'Operational alert smoke test. No research failure or benchmark claim is being reported.')])
            ledger.deliver(send)
        while True:
            candidates=[]
            for session in store.list_sessions():
                candidates.extend(alert_candidates(session,store.experiments(session['id'])))
            ledger.enqueue(candidates,baseline=first); first=False
            ledger.deliver(send)
            run.summary['monitor_heartbeat_utc']=datetime.now(timezone.utc).isoformat()
            if once:break
            time.sleep(30)
