"""Reconstruct and verify a validation winner, then publish its actual model and lineage."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import wandb
from wildfire_researcher import config, integrity, protocol, runner, tracking
from wildfire_researcher.execution import bounded, exclusive
from wildfire_researcher.model_bundle import load_model
from wildfire_researcher.state import Store


@exclusive
def preserve(session_id):
    store = Store(); session = store.get_session(session_id)
    eid = session['final_decision']['recommended_final_experiment_id']
    exp = store.get_experiment(session_id, eid)
    out = config.ARTIFACTS_DIR/'operations'/'preserved-winner'
    record_path = out/'publication.json'
    if record_path.exists():
        print(record_path.read_text()); return
    integrity.verified_cache(exp['experiment']['feature_protocol'], exp['experiment']['weather_days'])
    result = bounded(runner.run_experiment, exp['experiment'], session['research_seed'], out)
    old = np.load(exp['result']['predictions_path'])['y_score']
    new = np.load(result['predictions_path'])['y_score']
    if not np.allclose(old,new,rtol=0,atol=1e-7):
        raise ValueError('Reconstructed predictions do not match the recorded validation winner')
    data = protocol.load_research_splits(exp['experiment']['feature_protocol'], exp['experiment']['weather_days'])
    model, meta = load_model(result['model_bundle_path'])
    np.testing.assert_allclose(model.predict_proba(data['val']['X'])[:,1],new,rtol=0,atol=1e-7)
    dataset = integrity.dataset_manifest()
    dataset.update({'repository':protocol.DATASET_REPO,'source_commit':protocol.PINNED_COMMIT,
                    'kind':'reference-manifest','contains_raw_data':False,
                    'source_url':f'https://huggingface.co/datasets/{protocol.DATASET_REPO}/tree/{protocol.DATASET_REVISION}'})
    tracking.write_json(out/'dataset.json',dataset)
    config.load_wandb_credential()
    with wandb.init(entity=config.WANDB_ENTITY,project=config.WANDB_PROJECT,
                    name='operator-preserve-winner-20260913',job_type='model-preservation',
                    config={'source_session':session_id,'source_experiment':eid,'reconstructed':True,
                            'test_evaluated':False,'benchmark_comparable':False}) as run:
        d=wandb.Artifact('wildfireia-pinned-dataset',type='dataset',metadata=dataset)
        d.add_file(str(out/'dataset.json')); d.add_file(str(config.CANONICAL_DIR/'feature_manifest_natural.json'))
        logged=run.log_artifact(d,aliases=['pinned']); logged.wait(); run.use_artifact(logged)
        run.use_artifact(f'{config.WANDB_ENTITY}/{config.WANDB_PROJECT}/{session_id}-state:latest')
        run.use_artifact(f'{config.WANDB_ENTITY}/{config.WANDB_PROJECT}/{session_id}-{eid}-predictions:latest')
        metadata={'source_session':session_id,'source_experiment':eid,'source_run':exp['wandb_run_id'],
                  'reconstructed':True,'validation_predictions_match':True,
                  'validation_auprc':result['validation_auprc'],'test_evaluated':False,
                  'dataset_artifact':logged.qualified_name,'dataset_revision':protocol.DATASET_REVISION}
        art=wandb.Artifact('wildfireia-validation-winner',type='model',metadata=metadata)
        art.add_dir(result['model_bundle_path'])
        art.add_file(result['predictions_path'],name='predictions_val.npz')
        art.add_file(str(Path(__file__).resolve().parents[1]/'wildfire_researcher'/'model_bundle.py'),name='inference_reference.py')
        logged_model=run.log_artifact(art,aliases=['validation-winner','reconstructed']);logged_model.wait()
        run.summary.update({'reconstruction_validation_auprc':result['validation_auprc'],
                            'max_prediction_difference':float(np.max(np.abs(old-new)))})
        record={**metadata,'model_artifact':logged_model.qualified_name,'model_digest':logged_model.digest,
                'run_url':run.url,'registry_status':'not_linked'}
        tracking.write_json(record_path,record)
        print(json.dumps(record,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--session',default='wf-20260913-104003-2c71')
    preserve(p.parse_args().session)
