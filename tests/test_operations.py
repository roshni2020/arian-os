import json

import numpy as np
import pandas as pd
import pytest

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
