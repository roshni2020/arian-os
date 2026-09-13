"""Versioned inference assets; reconstructed models never inherit old test scores."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import integrity, protocol, tracking


def save_bundle(model, experiment, seed, data, out_dir, validation_auprc):
    out = Path(out_dir) / 'model'
    out.mkdir(parents=True, exist_ok=True)
    if experiment['model'] == 'xgboost':
        filename = 'model.ubj'
        model.save_model(out / filename)
    else:
        import joblib
        filename = 'model.joblib'
        joblib.dump(model, out / filename)
    metadata = {'format': 1, 'experiment': experiment, 'seed': seed,
                'model_file': filename, 'model_sha256': integrity.digest(out / filename),
                'feature_names': data['feature_names'],
                'preprocessing': data['metadata'].get('preprocessing', {}),
                'validation_auprc': validation_auprc, 'test_evaluated': False,
                'source_commit': protocol.PINNED_COMMIT, 'dataset_revision': protocol.DATASET_REVISION,
                'input_contract': 'Discovery-time columns from the pinned canonical feature pipeline; not raw incident JSON.'}
    tracking.write_json(out / 'manifest.json', metadata)
    return out


def load_model(bundle):
    bundle = Path(bundle)
    meta = json.loads((bundle / 'manifest.json').read_text())
    name = meta['model_file']
    if name not in ('model.ubj', 'model.joblib') or integrity.digest(bundle / name) != meta['model_sha256']:
        raise ValueError('Invalid model bundle or model hash mismatch')
    if name == 'model.ubj':
        from xgboost import XGBClassifier
        model = XGBClassifier()
        model.load_model(bundle / name)
    else:
        # Only load trusted project-owned joblib files. Never load an arbitrary uploaded pickle.
        import joblib
        model = joblib.load(bundle / name)
    return model, meta


def transform_frame(frame, meta):
    """Apply stored train-fitted statistics and exact feature order, without refitting."""
    p = meta['preprocessing']
    numeric, categorical = p['numeric_columns'], p['categorical_columns']
    missing = set(numeric + categorical) - set(frame.columns)
    if missing:
        raise ValueError(f'Missing canonical input columns: {sorted(missing)}')
    values = frame[numeric].apply(pd.to_numeric, errors='coerce').fillna(p['numeric_medians'])
    if p['scaler']['standardize'] and numeric:
        values = (values - pd.Series(p['scaler']['mean'])) / pd.Series(p['scaler']['scale'])
    cats = pd.get_dummies(frame[categorical].fillna('Unknown').astype(str), columns=categorical)
    cats = cats.reindex(columns=p['categorical_dummy_columns'], fill_value=0)
    result = pd.concat([values, cats], axis=1)
    if list(result.columns) != meta['feature_names']:
        raise ValueError('Inference feature ordering differs from the saved model')
    array = result.to_numpy(dtype=np.float32)
    if not np.isfinite(array).all():
        raise ValueError('Non-finite inference input')
    return array


def predict_frame(bundle, frame):
    model, meta = load_model(bundle)
    return np.asarray(model.predict_proba(transform_frame(frame, meta))[:, 1])
