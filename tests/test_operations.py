from datetime import datetime, timedelta, timezone
import json

import numpy as np
import pandas as pd
import pytest

from wildfire_researcher.notifications import AlertLedger, alert_candidates
from wildfire_researcher.model_bundle import save_bundle, load_model, transform_frame


@pytest.mark.parametrize('status',['awaiting_aria_proposal','error','cancelled'])
def test_launch_resume_cannot_start_artifact_controller(tmp_path,monkeypatch,status):
    from fastapi.testclient import TestClient
    from wildfire_researcher import api
    from wildfire_researcher.state import Store
    st=Store(tmp_path/'resume.sqlite')
    st.create_session(session_id='launch-test',budget=2,aria_mode='connected',
                      research_seed=1,fast_mode=False,limit_train_samples=None,entity='e',project='p')
    st.update_session('launch-test',protocol_json=json.dumps({'execution_backend':'wandb-launch'}),
                      status=status,cancel_requested=True,error='Retain diagnostic')
    monkeypatch.setattr(api,'_store',st)
    def unexpected(*args,**kwargs):raise AssertionError('Must not start a second controller')
    monkeypatch.setattr(api,'_start_worker',unexpected)
    response=TestClient(api.app).post('/api/sessions/launch-test/resume',json={})
    assert response.status_code==409 and 'Launch' in response.json()['detail']
    assert st.get_session('launch-test')['cancel_requested']
    assert st.get_session('launch-test')['error']=='Retain diagnostic'


def session(**updates):
    return {'id':'s','aria_mode':'connected','status':'complete','budget':2,
            'state_revision':3,'updated_at':datetime.now(timezone.utc).isoformat(),**updates}


def test_historical_benchmark_flag_does_not_emit_certified_alert():
    alerts=alert_candidates(session(final_evaluation={'benchmark_beaten':True,'mean_test_auprc':0.55}),[])
    assert alerts[0][2]=='Test evaluation recorded'
    assert 'certification unavailable' in alerts[0][3]


def test_alert_retry_dedup_and_historical_suppression(tmp_path):
    ledger=AlertLedger(tmp_path/'alerts.sqlite')
    candidate=('one','INFO','Test','body')
    ledger.enqueue([('old','INFO','old','old')],baseline=True)
    ledger.enqueue([candidate,candidate])
    ledger.deliver(lambda *args: (_ for _ in ()).throw(RuntimeError('offline')))
    received=[]
    ledger.deliver(lambda *args:received.append(args))
    ledger.deliver(lambda *args:received.append(args))
    assert received==[candidate]


def test_stall_has_revision_identity_and_ignores_completed():
    past=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    assert not alert_candidates(session(updated_at=past),[])
    a=alert_candidates(session(updated_at=past,status='awaiting_aria_proposal'),[])
    assert a[0][0]=='s:stall:3'
    assert not alert_candidates(session(updated_at=past,status='awaiting_aria_proposal',aria_mode='fallback'),[])


def test_bundle_reload_and_tamper_rejection(tmp_path):
    from sklearn.linear_model import LogisticRegression
    X=np.array([[0.,0.],[1.,0.],[0.,1.],[1.,1.]])
    m=LogisticRegression().fit(X,[0,0,1,1])
    bundle=save_bundle(m,{'model':'logistic_regression'},1,
                       {'feature_names':['a','b'],'metadata':{}},tmp_path,0.5)
    loaded,_=load_model(bundle)
    np.testing.assert_array_equal(loaded.predict_proba(X),m.predict_proba(X))
    (bundle/'model.joblib').write_bytes(b'altered')
    with pytest.raises(ValueError,match='hash'):load_model(bundle)


def test_inference_uses_training_statistics_and_ignores_unseen_categories():
    meta={'feature_names':['x','cat_a'],'preprocessing':{
        'numeric_columns':['x'],'categorical_columns':['cat'],'numeric_medians':{'x':4.},
        'scaler':{'standardize':True,'mean':{'x':2.},'scale':{'x':2.}},'categorical_dummy_columns':['cat_a']}}
    X=transform_frame(pd.DataFrame({'x':[None,8.],'cat':['a','unseen']}),meta)
    np.testing.assert_array_equal(X,np.array([[1,1],[3,0]],dtype=np.float32))
    with pytest.raises(ValueError,match='Missing'):transform_frame(pd.DataFrame({'x':[1.]}),meta)


def test_launch_request_requires_opted_in_session_and_rejects_test_access():
    from wildfire_researcher.launch_step import validate_request
    s=session(protocol={'execution_backend':'wandb-launch'},limit_train_samples=None,
              cancel_requested=False,status='created')
    validate_request({'session_id':'s','action':'baseline'},s)
    for req in ({'session_id':'s','action':'final-eval'},
                {'session_id':'s','action':'baseline','command':'anything'},
                {'session_id':'other','action':'baseline'}):
        with pytest.raises(ValueError):validate_request(req,s)
    with pytest.raises(ValueError):validate_request({'session_id':'s','action':'baseline'},dict(s,protocol={}))
    with pytest.raises(ValueError):validate_request({'session_id':'s','action':'baseline'},dict(s,cancel_requested=True))


def test_launch_session_persists_backend_opt_in(tmp_path,monkeypatch):
    from wildfire_researcher import config
    from wildfire_researcher.launch_step import create_launch_session
    monkeypatch.setattr(config,'DB_PATH',tmp_path/'launch.sqlite')
    s=create_launch_session(2)
    assert s['protocol']['execution_backend']=='wandb-launch'
    assert s['budget']==2 and s['id'].startswith('launch-')
