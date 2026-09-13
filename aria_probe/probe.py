"""Real ARIA integration probe. Synthetic data; never a WildfireIA score."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time


def validate(proposal, history):
    required = {'observation', 'hypothesis', 'reason', 'experiment', 'previous_decision'}
    if not isinstance(proposal, dict) or not required <= proposal.keys():
        raise ValueError('Missing required proposal fields')
    for key in ('observation', 'hypothesis', 'reason'):
        if not isinstance(proposal[key], str) or not proposal[key].strip():
            raise ValueError(f'{key} must be nonempty text')
    exp = proposal['experiment']
    if not isinstance(exp, dict) or set(exp) != {'model', 'feature_count', 'C', 'class_weight'}:
        raise ValueError('Only model, feature_count, C, class_weight are allowed')
    if exp['model'] != 'logistic_regression':
        raise ValueError('Only logistic_regression is allowed in this probe')
    if type(exp['feature_count']) is not int or exp['feature_count'] not in (2, 4, 8, 12):
        raise ValueError('feature_count must be 2, 4, 8, or 12')
    if type(exp['C']) not in (float, int) or not math.isfinite(exp['C']) or not 0.01 <= exp['C'] <= 10:
        raise ValueError('C must be finite and between 0.01 and 10')
    if exp['class_weight'] not in (None, 'balanced'):
        raise ValueError('Invalid class_weight')
    exp = dict(exp, C=float(exp['C']))
    if any(row['experiment'] == exp for row in history):
        raise ValueError('Duplicate experiment')
    decision = proposal['previous_decision']
    if not isinstance(decision, dict) or decision.get('decision') not in ('KEEP', 'REJECT'):
        raise ValueError('previous_decision requires KEEP or REJECT')
    if not all(isinstance(decision.get(k), str) and decision[k].strip() for k in ('reason', 'learning')):
        raise ValueError('Decision requires reason and learning')
    return exp


def credential():
    if not os.environ.get('WANDB_API_KEY') and os.name == 'nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            os.environ['WANDB_API_KEY'] = winreg.QueryValueEx(key, 'WANDB_API_KEY')[0]
    if not os.environ.get('WANDB_API_KEY'):
        raise RuntimeError('WANDB_API_KEY is required')


def run(args):
    credential()
    import numpy as np
    import wandb
    import weave
    from sklearn.datasets import make_classification
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_fscore_support, confusion_matrix, precision_recall_curve
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    project = f'{args.entity}/{args.project}'
    client = weave.init(project)
    api = wandb.Api()
    folder = Path('artifacts') / args.session
    folder.mkdir(parents=True, exist_ok=True)
    state_path = folder / 'state.json'
    baseline = {'model': 'logistic_regression', 'feature_count': 2, 'C': 1.0, 'class_weight': None}
    state = json.loads(state_path.read_text()) if state_path.exists() else {
        'session_id': args.session, 'score_kind': 'SYNTHETIC_INTEGRATION_TEST',
        'benchmark_comparable': False, 'aria_mode': 'awaiting_real_aria',
        'max_aria_experiments': 2, 'history': [], 'decisions': [], 'status': 'starting',
        'contract': 'Fixed 1200 synthetic samples; seed 42; stratified 75/25 train/validation split. No test set and no WildfireIA claim.',
        'feature_context': 'First 4 generated columns are informative, next 4 redundant, last 4 noise. Baseline uses first 2. All comparisons use the same split.',
        'allowed': {'model': ['logistic_regression'], 'feature_count': [2,4,8,12], 'C_range': [0.01,10], 'class_weight': [None,'balanced']},
    }

    @weave.op()
    def validate_experiment(proposal, history):
        return validate(proposal, history)

    @weave.op()
    def execute_training(experiment):
        start = time.monotonic()
        X, y = make_classification(n_samples=1200, n_features=12, n_informative=4,
                                  n_redundant=4, weights=[0.85,0.15], flip_y=0.04,
                                  shuffle=False, random_state=42)
        ids = np.arange(len(y))
        train, val = train_test_split(ids, test_size=0.25, random_state=42, stratify=y)
        n = experiment['feature_count']
        model = make_pipeline(StandardScaler(), LogisticRegression(C=experiment['C'],
                    class_weight=experiment['class_weight'], max_iter=300, random_state=42))
        model.fit(X[train,:n],y[train])
        score = model.predict_proba(X[val,:n])[:,1]
        pred = (score >= 0.5).astype(int)
        p,r,f,_ = precision_recall_fscore_support(y[val],pred,average='binary',zero_division=0)
        curve_p,curve_r,thresholds = precision_recall_curve(y[val],score)
        result = {'validation_auprc': float(average_precision_score(y[val],score)),
            'validation_auroc': float(roc_auc_score(y[val],score)), 'precision':float(p),'recall':float(r),'f1':float(f),
            'confusion_matrix':confusion_matrix(y[val],pred).tolist(),
            'false_negative_count':int(((pred==0)&(y[val]==1)).sum()),
            'false_positive_count':int(((pred==1)&(y[val]==0)).sum()),
            'coefficients':model[-1].coef_[0].tolist(), 'runtime_seconds':time.monotonic()-start,
            'split_sha256':hashlib.sha256(val.tobytes()).hexdigest()}
        np.savez(folder / f'predictions-{len(state["history"])}.npz', ids=val, labels=y[val], scores=score,
                 precision=curve_p, recall=curve_r, thresholds=thresholds)
        return result

    @weave.op()
    def receive_aria_proposal(proposal, source_artifact):
        return {'proposal':proposal,'source_artifact':source_artifact,
                'provenance':'Produced externally; review ARIA conversation for authorship. No fabricated internal ARIA spans.'}

    def save():
        temp = state_path.with_suffix('.tmp')
        temp.write_text(json.dumps(state, indent=2))
        temp.replace(state_path)

    def publish(wrun):
        state['remaining_experiment_budget'] = 2-max(0,len(state['history'])-1)
        state['current_best_validation_auprc'] = max(x['result']['validation_auprc'] for x in state['history'])
        save()
        artifact = wandb.Artifact(f'{args.session}-state', type='research-state', metadata={'benchmark_comparable':False})
        artifact.add_file(str(state_path), name='state.json')
        wrun.log_artifact(artifact, aliases=['latest']).wait()

    def experiment(exp, proposal=None, source=None):
        index = len(state['history'])
        with wandb.init(entity=args.entity,project=args.project,group=args.session,
                       name=f'{args.session}-exp-{index}',job_type='integration-probe',
                       config={'session_id':args.session,'experiment':exp,'proposal':proposal,
                               'controller':'ARIA' if proposal else 'baseline_setup',
                               'benchmark_comparable':False,'score_kind':'SYNTHETIC_INTEGRATION_TEST'}) as wrun:
            client.set_wandb_run_context(run_id=wrun.id)
            if proposal:
                receive_aria_proposal(proposal,source)
                validate_experiment(proposal,state['history'])
                state['decisions'].append({'experiment_index':index-1,**proposal['previous_decision'],'source':source})
                state['aria_mode']='connected_via_artifacts'
            result = execute_training(exp)
            wrun.log({k:v for k,v in result.items() if isinstance(v,(int,float))})
            state['history'].append({'iteration':index,'experiment':exp,'proposal':proposal,'result':result,'wandb_run_url':wrun.url})
            state['status']='awaiting_aria_proposal' if index < 2 else 'awaiting_final_aria_decision'
            publish(wrun)
            evidence = wandb.Artifact(f'{args.session}-predictions-{index}',type='predictions')
            evidence.add_file(str(folder / f'predictions-{index}.npz'))
            wrun.log_artifact(evidence).wait()
            print(json.dumps({'iteration':index,'result':result,'url':wrun.url}),flush=True)
        client.clear_wandb_run_context()

    if not state['history']:
        experiment(baseline)
    if args.command == 'baseline':
        return
    deadline = time.monotonic()+args.wait_seconds
    while time.monotonic() < deadline:
        number = len(state['history'])
        final = number > 2
        if state['status'] == 'complete':
            return
        ref = f'{project}/{args.session}-decision-final:latest' if final else f'{project}/{args.session}-proposal-{number}:latest'
        try:
            artifact = api.artifact(ref,type='research-decision' if final else 'research-proposal')
        except wandb.errors.CommError as exc:
            if 'not found' not in str(exc).lower() and 'does not exist' not in str(exc).lower():
                raise
            time.sleep(10)
            continue
        source = f'{artifact.qualified_name.rsplit(":", 1)[0]}:{artifact.version}'
        root = artifact.download(root=str(folder / f'proposal-{number}'))
        if final:
            decision = json.loads((Path(root)/'decision.json').read_text())
            if decision.get('decision') not in ('KEEP','REJECT') or not all(isinstance(decision.get(k),str) and decision[k].strip() for k in ('reason','learning')):
                raise ValueError('Final decision needs decision, reason, learning')
            with wandb.init(entity=args.entity,project=args.project,group=args.session,
                           name=f'{args.session}-final',job_type='aria-decision',config={'benchmark_comparable':False}) as wrun:
                client.set_wandb_run_context(run_id=wrun.id)
                receive_aria_proposal(decision,source)
                state['decisions'].append({'experiment_index':number-1,**decision,'source':source})
                state['status']='complete'
                publish(wrun)
            client.clear_wandb_run_context()
            print('Two ARIA-selected experiments and final decision complete.',flush=True)
            return
        proposal = json.loads((Path(root)/'proposal.json').read_text())
        exp = validate(proposal,state['history'])
        experiment(exp,proposal,source)
    print('No proposal arrived before deadline. State preserved; no fallback experiment executed.',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['baseline','watch'])
    parser.add_argument('--entity',default='ali-amjad52114-r42')
    parser.add_argument('--project',default='aria-integration-probe')
    parser.add_argument('--session',default='aria-probe-20260913')
    parser.add_argument('--wait-seconds',type=int,default=600)
    run(parser.parse_args())
