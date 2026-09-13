import json
import time
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from wildfire_researcher import config, protocol, final_eval, integrity, execution, tracking
from wildfire_researcher.state import Store


@pytest.fixture
def frozen_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    monkeypatch.setattr(config,'ARTIFACTS_DIR',tmp_path/'artifacts')
    store=Store(tmp_path/'research.sqlite')
    s=store.create_session(session_id='wf-audit',budget=1,aria_mode='connected',research_seed=553371,
       fast_mode=False,limit_train_samples=None,entity='test',project='test')
    exp={'model':'logistic_regression','feature_protocol':'metadata','weather_days':5,'hyperparameters':{'C':1.,'class_weight':'balanced'}}
    store.claim_experiment(s['id'],experiment=exp,config_key='one',controller='ARIA',proposal=None,
        proposal_source=None,parent_experiment_id=None,change_summary='baseline')
    store.update_experiment(s['id'],'exp-000',status='complete')
    store.update_session(s['id'],status='complete',final_decision={'recommended_final_experiment_id':'exp-000'})
    return store,s['id']


@pytest.mark.parametrize('seeds',[[1],[],[553371]*5,[553371,553372,553373,553374,True]])
def test_custom_or_duplicate_seeds_blocked(frozen_ready,seeds):
    store,sid=frozen_ready
    with pytest.raises(ValueError): final_eval.prepare_freeze(store,sid,'exp-000',seeds)


@pytest.mark.parametrize('fields',[{'status':'training'},{'final_decision':None},{'aria_mode':'fallback'},{'limit_train_samples':100}])
def test_unready_evaluation_blocked(frozen_ready,fields):
    store,sid=frozen_ready
    store.update_session(sid,**fields)
    with pytest.raises(ValueError): final_eval.prepare_freeze(store,sid,'exp-000',protocol.FINAL_EVAL_SEEDS)


def test_freeze_is_immutable_and_existing_result_idempotent(frozen_ready):
    store,sid=frozen_ready
    final_eval.prepare_freeze(store,sid,'exp-000',protocol.FINAL_EVAL_SEEDS)
    e=store.get_experiment(sid,'exp-000')['experiment'];e['hyperparameters']['C']=2
    store.update_experiment(sid,'exp-000',experiment_json=json.dumps(e))
    with pytest.raises(ValueError,match='identity'): final_eval.prepare_freeze(store,sid,'exp-000',protocol.FINAL_EVAL_SEEDS)
    result={'experiment_id':'exp-000','seeds':protocol.FINAL_EVAL_SEEDS,'mean_test_auprc':.54}
    store.update_session(sid,final_evaluation=result)
    assert final_eval.evaluate_frozen(store,sid,'exp-000',tracking_enabled=False)==result
    with pytest.raises(ValueError): final_eval.evaluate_frozen(store,sid,'exp-000',seeds=[1],tracking_enabled=False)


def test_unknown_revision_fails_closed(monkeypatch):
    monkeypatch.setattr(protocol,'repo_commit',lambda:None)
    assert final_eval.comparable({'feature_protocol':'all'},{'limit_train_samples':None})[0] is False
    with pytest.raises(ValueError):integrity.require_clean_code()


def test_historical_claim_is_not_certified():
    record={'mean_test_auprc':.54,'benchmark_beaten':True}
    view=final_eval.evaluation_view(record)
    assert view['reported_above_reference'] and not view['benchmark_beaten']
    assert record['benchmark_beaten'] # original evidence is unchanged


def test_dataset_tamper_rejected(tmp_path,monkeypatch):
    from wildfire_researcher import cli
    monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    monkeypatch.setattr(config,'CANONICAL_DIR',tmp_path)
    monkeypatch.setattr(cli,'CANONICAL_FILES',['one'])
    (tmp_path/'one').write_text('original')
    (tmp_path/'verified_dataset.json').write_text(json.dumps({'dataset_revision':protocol.DATASET_REVISION,'files':{'one':integrity.digest(tmp_path/'one')}}))
    integrity.dataset_manifest()
    (tmp_path/'one').write_text('changed')
    with pytest.raises(ValueError,match='changed'): integrity.dataset_manifest()


def test_research_loader_does_not_open_test_files(tmp_path,monkeypatch):
    monkeypatch.setattr(protocol,'ensure_tabular_cache',lambda *a:tmp_path)
    (tmp_path/'metadata.json').write_text('{}')
    (tmp_path/'feature_names.json').write_text('{"feature_names":["x"]}')
    for split in ('train','val'):
        np.save(tmp_path/f'X_{split}.npy',[[1.]])
        np.save(tmp_path/f'y_{split}.npy',[1])
        np.save(tmp_path/f'fire_id_{split}.npy',['id'])
        pd.DataFrame({'fire_id':['id']}).to_parquet(tmp_path/f'sample_index_{split}.parquet')
    assert set(protocol.load_research_splits('metadata')) >= {'train','val'}
    assert not list(tmp_path.glob('*test*'))


def test_training_timeout_and_cancellation():
    with pytest.raises(TimeoutError): execution.bounded(time.sleep,10,timeout=.15)
    with pytest.raises(InterruptedError): execution.bounded(time.sleep,10,timeout=10,should_cancel=lambda:True)


def test_worker_lease_excludes_second_worker(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    with execution.worker_lease():
        with pytest.raises(RuntimeError,match='active'):
            with execution.worker_lease():pass
    with execution.worker_lease():pass


def test_trace_context_links_run_and_cleans_up(monkeypatch):
    from contextlib import nullcontext
    client=Mock()
    monkeypatch.setattr(tracking,'init_weave',lambda *a:client)
    monkeypatch.setattr(tracking,'_weave',Mock(attributes=lambda a:nullcontext()))
    with tracking.research_context('e','p','sid','run1',3):
        client.set_wandb_run_context.assert_called_once_with(run_id='run1')
    client.clear_wandb_run_context.assert_called_once()


def test_preprocessing_train_unchanged_when_heldout_changes():
    dl=protocol.official().dataloader
    train=pd.DataFrame({'x':[1.,np.nan,3.],'category':['a','b','a']})
    val=pd.DataFrame({'x':[9.,10.],'category':['z','a']})
    first, names, _=dl.fit_transform_event_features(train,val,val,['x','category'],True)
    altered=val.assign(x=[1e9,-1e9],category=['new','new'])
    second, second_names, _=dl.fit_transform_event_features(train,altered,altered,['x','category'],True)
    np.testing.assert_array_equal(first['train'],second['train'])
    assert names==second_names


def test_final_evaluation_persists_seed_predictions_and_replay(frozen_ready,monkeypatch):
    store,sid=frozen_ready
    monkeypatch.setattr(integrity,'verified_cache',lambda *a:{'verified':'fixture'})
    monkeypatch.setattr(protocol,'repo_commit',lambda:protocol.PINNED_COMMIT)
    data={s:{'X':np.array([[0.],[1.],[2.],[3.]]),'y':np.array([0,1,0,1]),'fire_id':np.array(['a','b','c','d'])} for s in ('train','val','test')}
    monkeypatch.setattr(protocol,'load_sealed_test_split',lambda *a:data)
    # Exercise the real final evaluator with a tiny synthetic fixture, never 2020.
    monkeypatch.setattr(final_eval,'bounded',lambda fn,*a,**k:fn(*a))
    result=final_eval.evaluate_frozen(store,sid,'exp-000',tracking_enabled=False)
    assert len(result['prediction_files'])==5
    assert result['benchmark_beaten'] is False and result['claim_eligible'] is False
    folder=config.ARTIFACTS_DIR/sid
    replay=json.loads((folder/'replay.json').read_text())
    assert replay['session']['final_evaluation']==result
    monkeypatch.setattr(protocol,'load_sealed_test_split',Mock(side_effect=AssertionError('repeat test access')))
    assert final_eval.evaluate_frozen(store,sid,'exp-000',tracking_enabled=False)==result


def test_freeze_discloses_prior_test_exposure(frozen_ready):
    store,sid=frozen_ready
    old=store.create_session(session_id='wf-old',budget=1,aria_mode='connected',research_seed=1,fast_mode=False,limit_train_samples=None,entity='e',project='p')
    store.update_session(old['id'],final_evaluation={'mean_test_auprc':.54})
    assert final_eval.prepare_freeze(store,sid,'exp-000',protocol.FINAL_EVAL_SEEDS)[3]==['wf-old']


def test_interrupted_final_evaluation_resumes_saved_seeds(frozen_ready,monkeypatch):
    store,sid=frozen_ready
    monkeypatch.setattr(integrity,'verified_cache',lambda *a:{'verified':'fixture'})
    monkeypatch.setattr(protocol,'repo_commit',lambda:protocol.PINNED_COMMIT)
    data={s:{'X':np.array([[0.],[1.],[2.],[3.]]),'y':np.array([0,1,0,1]),'fire_id':np.array(['a','b','c','d'])} for s in ('train','val','test')}
    monkeypatch.setattr(protocol,'load_sealed_test_split',lambda *a:data)
    trained=[]
    def fail_once(fn,*args):
        if len(trained)==2: raise RuntimeError('simulated interruption')
        trained.append(args[1]); return fn(*args)
    monkeypatch.setattr(final_eval,'bounded',fail_once)
    with pytest.raises(RuntimeError,match='interruption'):
        final_eval.evaluate_frozen(store,sid,'exp-000',tracking_enabled=False)
    def finish(fn,*args):
        trained.append(args[1]); return fn(*args)
    monkeypatch.setattr(final_eval,'bounded',finish)
    result=final_eval.evaluate_frozen(store,sid,'exp-000',tracking_enabled=False)
    assert trained==protocol.FINAL_EVAL_SEEDS
    assert len(result['per_seed'])==5
