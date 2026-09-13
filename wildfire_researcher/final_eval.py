"""Official held-out evaluation of ONE frozen configuration.

Run once, after the research loop ends and ARIA has recommended a configuration. Trains on the
official train years (early stopping on the validation year exactly as the official script does),
scores the sealed 2020 test year with the official metric code over several seeds, and gates the
benchmark claim in the backend: strictly greater than 0.533 mean test AUPRC on a protocol-matched
run, otherwise no claim.
"""
from __future__ import annotations

import time
import json
from pathlib import Path
from typing import Any

import numpy as np

from . import config, protocol, runner, tracking
from .state import Store
from .execution import exclusive, bounded
from . import integrity


def evaluation_view(result):
    """Preserve historical evidence, but never promote a legacy flag to a verified claim."""
    if not result:
        return result
    out = dict(result)
    out['reported_above_reference'] = result['mean_test_auprc'] > protocol.PUBLISHED_TEST_AUPRC
    out['benchmark_beaten'] = bool(result.get('claim_eligible') and result.get('benchmark_beaten'))
    out['claim_note'] = result.get('claim_note', 'Historical result: test-access freeze and integrity gates were not enforced. Exact paper seeds are unavailable; session 2 followed session 1 test disclosure.')
    return out


def prepare_freeze(store, session_id, experiment_id, seeds):
    from .state import now
    if seeds != protocol.FINAL_EVAL_SEEDS or any(type(x) is not int for x in seeds) or len(set(seeds)) != 5:
        raise ValueError('Official evaluation requires the five predeclared unique seeds; custom seed selection is prohibited')
    with store.connect() as conn:
        session = store.get_session(session_id)
        experiment = store.get_experiment(session_id, experiment_id)
        existing = session.get('final_evaluation')
        if existing:
            if existing['experiment_id'] != experiment_id or existing['seeds'] != seeds:
                raise ValueError('This session already evaluated a different frozen configuration or seed list')
            return session, experiment, existing, None
        if session['status'] not in ('complete','final_evaluation') or experiment['status'] != 'complete':
            raise ValueError('Research and selected experiment must be complete before test access')
        if (session.get('final_decision') or {}).get('recommended_final_experiment_id') != experiment_id:
            raise ValueError('Only the final ARIA recommendation may be evaluated')
        if session['aria_mode'] != 'connected' or session.get('limit_train_samples'):
            raise ValueError('Development or fallback sessions are not eligible for official evaluation')
        identity = {'experiment_id':experiment_id, 'experiment':experiment['experiment'], 'seeds':seeds,
                    'protocol':session['protocol'], 'implementation':{name:integrity.digest(Path(__file__).with_name(name))
                         for name in ('runner.py','final_eval.py','protocol.py')}}
        row = conn.execute('SELECT * FROM final_evaluation_freezes WHERE session_id=?',(session_id,)).fetchone()
        if row:
            if json.loads(row['identity_json']) != identity:
                raise ValueError('Frozen evaluation identity changed')
            exposure = json.loads(row['prior_test_exposure_json'])
        else:
            exposure = [r[0] for r in conn.execute('SELECT id FROM sessions WHERE final_evaluation_json IS NOT NULL AND id<>? UNION SELECT session_id FROM final_evaluation_freezes WHERE session_id<>?',(session_id,session_id))]
            conn.execute('INSERT INTO final_evaluation_freezes VALUES (?,?,?,?)',
                (session_id,now(),json.dumps(identity,sort_keys=True),json.dumps(exposure)))
        return session, experiment, None, exposure


def fit_seed(exp, seed, data, path):
    model, notes = runner._fit_model(exp, seed, data['train']['X'],data['train']['y'].astype(int),
                                    data['val']['X'],data['val']['y'].astype(int))
    temp = path.with_suffix('.tmp.npz')
    np.savez_compressed(temp, val_score=runner._predict(model,data['val']['X']),
        test_score=runner._predict(model,data['test']['X']), y_val=data['val']['y'],
        y_test=data['test']['y'], test_fire_id=data['test']['fire_id'], notes=json.dumps(notes))
    temp.replace(path)
    tracking.write_json(path.with_suffix('.sha256.json'), {'sha256':integrity.digest(path)})


def comparable(experiment: dict[str, Any], session: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    if experiment["feature_protocol"] == "firms":
        reasons.append("the 'firms' protocol restricts the sample to VIIRS-matched events and is not the published cohort")
    if session.get("limit_train_samples"):
        reasons.append("session trained on a subsample (DEV)")
    if protocol.repo_commit() != protocol.PINNED_COMMIT:
        reasons.append("local WildfireIA code is not the pinned revision")
    return (not reasons), reasons


@exclusive
def evaluate_frozen(store: Store, session_id: str, experiment_id: str, seeds: list[int] | None = None, tracking_enabled: bool = True) -> dict[str, Any]:
    seeds = protocol.FINAL_EVAL_SEEDS if seeds is None else seeds
    session, experiment, existing, prior_exposure = prepare_freeze(store, session_id, experiment_id, seeds)
    if existing:
        return existing
    exp = experiment["experiment"]
    is_comparable, why_not = comparable(exp, session)
    if not is_comparable:
        raise ValueError('; '.join(why_not))
    attestation = integrity.verified_cache(exp['feature_protocol'], exp['weather_days'])
    store.set_status(session_id, "final_evaluation", f"Official test evaluation of {experiment_id} over seeds {seeds}")
    data = protocol.load_sealed_test_split(exp["feature_protocol"], exp["weather_days"])
    X_train, y_train = data["train"]["X"], data["train"]["y"].astype(int)
    X_val, y_val = data["val"]["X"], data["val"]["y"].astype(int)
    X_test, y_test = data["test"]["X"], data["test"]["y"].astype(int)
    per_seed = []
    start = time.monotonic()
    for seed in seeds:
        pred_path = config.ARTIFACTS_DIR/session_id/f'final-seed-{seed}.npz'
        pred_path.parent.mkdir(parents=True, exist_ok=True)
        signature = pred_path.with_suffix('.sha256.json')
        if not pred_path.exists() or not signature.exists():
            bounded(fit_seed, exp, seed, data, pred_path)
        if integrity.digest(pred_path) != json.loads(signature.read_text())['sha256']:
            raise ValueError('Saved final predictions changed; refusing to overwrite evidence')
        saved = np.load(pred_path,allow_pickle=True)
        if not np.array_equal(saved['y_val'], y_val) or not np.array_equal(saved['y_test'], y_test):
            raise ValueError('Saved seed prediction labels changed')
        val_score, test_score = saved['val_score'], saved['test_score']
        if not np.isfinite(val_score).all() or not np.isfinite(test_score).all():
            raise ValueError('Final scores contain nonfinite values')
        notes = json.loads(str(saved['notes']))
        val_metrics, threshold = protocol.classification_metrics(y_val, val_score)
        tr = protocol.official().train
        test_metrics = {k: float(v) for k, v in tr.classification_metrics(y_test, test_score, threshold).items()}
        per_seed.append({"seed": seed, "val_auprc": val_metrics["auprc"], "test_auprc": test_metrics["auprc"], "test_auroc": test_metrics["auroc"], "test_f1": test_metrics["f1"], "test_precision": test_metrics["precision"], "test_recall": test_metrics["recall"], "test_recall_at_5": test_metrics["recall_at_5"], "threshold_from_val": threshold, "fit_notes": notes})
    test_scores = np.array([r["test_auprc"] for r in per_seed])
    mean, std = float(test_scores.mean()), float(test_scores.std(ddof=1)) if len(test_scores) > 1 else 0.0
    # Exact paper seed reproduction and a fresh confirmatory holdout are not established.
    beaten = False
    result = {
        "score_kind": "OFFICIAL_TEST_AUPRC",
        "experiment_id": experiment_id,
        "experiment": exp,
        "seeds": seeds,
        "per_seed": per_seed,
        "mean_test_auprc": mean,
        "std_test_auprc": std,
        "mean_val_auprc": float(np.mean([r["val_auprc"] for r in per_seed])),
        "published_test_auprc": protocol.PUBLISHED_TEST_AUPRC,
        "delta_vs_published": mean - protocol.PUBLISHED_TEST_AUPRC,
        "protocol_matched": is_comparable,
        "not_comparable_reasons": why_not,
        "benchmark_beaten": beaten,
        'reported_above_reference':bool(mean > protocol.PUBLISHED_TEST_AUPRC),
        'claim_eligible':False,
        'claim_note':'Recorded test mean compared with published reference; exact paper seeds are unavailable. Prior local test exposures are disclosed separately. This is not a certified superiority claim.',
        'prior_test_exposure_sessions':prior_exposure,
        'integrity_attestation':attestation,
        'prediction_files':{str(s):integrity.digest(config.ARTIFACTS_DIR/session_id/f'final-seed-{s}.npz') for s in seeds},
        "seed_note": "The official repository names seed 553371 only; the published 0.533 is a five-seed mean whose seed list is not public. These five seeds are ours.",
        "test_size": int(len(y_test)),
        "test_positives": int((y_test == 1).sum()),
        "runtime_seconds": time.monotonic() - start,
        "provenance": protocol.provenance(),
    }
    if tracking_enabled:
        with tracking.ExperimentRun(entity=session["wandb_entity"], project=session["wandb_project"], session_id=session_id, experiment_id=experiment_id, iteration=-1, run_kind="final-evaluation", exp_config={"experiment": exp, "seeds": seeds, "score_kind": "OFFICIAL_TEST_AUPRC", "benchmark_comparable": is_comparable, "protocol": session["protocol"]}, tags=["score_kind:OFFICIAL_TEST_AUPRC"]) as run:
            run.log({"mean_test_auprc": mean, "std_test_auprc": std, "published_test_auprc": protocol.PUBLISHED_TEST_AUPRC, "delta_vs_published": result["delta_vs_published"]})
            run.log_table("per_seed", ["seed", "val_auprc", "test_auprc", "test_auroc", "test_recall_at_5"], [[r["seed"], r["val_auprc"], r["test_auprc"], r["test_auroc"], r["test_recall_at_5"]] for r in per_seed])
            run.summary({"benchmark_beaten": beaten, "protocol_matched": is_comparable})
            result["wandb_run_url"] = run.url
            path = config.ARTIFACTS_DIR / session_id / "final_evaluation.json"
            tracking.write_json(path, result)
            run.log_artifact(f"{session_id}-final-evaluation", "final-evaluation", {'final_evaluation.json':path,
                **{f'predictions-{s}.npz':config.ARTIFACTS_DIR/session_id/f'final-seed-{s}.npz' for s in seeds}}, metadata={"benchmark_beaten": beaten, "protocol_matched": is_comparable})
    else:
        tracking.write_json(config.ARTIFACTS_DIR / session_id / "final_evaluation.json", result)
    store.update_session(session_id, final_evaluation=result)
    store.set_status(session_id, "complete", f"Recorded test AUPRC {mean:.4f} ± {std:.4f} for {experiment_id}; benchmark certification unavailable")
    from .loop import replay_record
    tracking.write_json(config.ARTIFACTS_DIR/session_id/'replay.json', replay_record(store,session_id))
    return result
