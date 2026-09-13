"""Read-only check that local session records match W&B runs, artifacts and Weave calls.

Usage: python scripts/verify_remote.py --session wf-20260913-live1
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wildfire_researcher import config, tracking  # noqa: E402
from wildfire_researcher.state import Store  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--session", required=True)
args = parser.parse_args()

config.load_wandb_credential()
import wandb  # noqa: E402

store = Store()
session = store.get_session(args.session)
api = wandb.Api()
project = f"{session['wandb_entity']}/{session['wandb_project']}"
problems = []
runs = []
for e in store.completed_experiments(args.session):
    if not e["wandb_run_id"]:
        problems.append(f"{e['id']} has no W&B run id")
        continue
    r = api.run(f"{project}/{e['wandb_run_id']}")
    remote = float(r.summary.get("validation_auprc", float("nan")))
    if not math.isfinite(remote) or abs(remote - e["score"]) > 1e-9:
        problems.append(f"{e['id']} remote auprc {remote} != local {e['score']}")
    if r.state != 'finished':
        problems.append(f"{e['id']} remote run is not finished")
    if r.config.get("benchmark_comparable") is not False:
        problems.append(f"{e['id']} run config lacks benchmark_comparable=false")
    if "WANDB_API_KEY" in json.dumps(dict(r.config)):
        problems.append(f"{e['id']} run config leaks a key")
    runs.append({"id": r.id, "name": r.name, "state": r.state, "auprc": remote, "controller": r.config.get("controller")})
artifacts = {}
for name, kind in [(f"{args.session}-state", "research-state"), (f"{args.session}-decision-final", "research-decision")]:
    try:
        a = api.artifact(f"{project}/{name}:latest", type=kind)
        artifacts[name] = {"version": a.version, "digest": a.digest}
    except Exception as exc:  # noqa: BLE001
        artifacts[name] = f"missing ({type(exc).__name__})"
        problems.append(f'Missing required artifact: {name}')
for m in store.aria_messages(args.session):
    if m["direction"] == "inbound" and m["accepted"] and m["artifact_ref"]:
        ref = m["artifact_ref"]
        try:
            a = api.artifact(ref if ":" in ref else ref + ":latest")
            if a.digest != m["artifact_digest"]:
                problems.append(f"digest mismatch for {ref}")
            artifacts[ref] = {"version": a.version, "digest": a.digest}
        except Exception as exc:  # noqa: BLE001
            problems.append(f"cannot fetch {ref}: {type(exc).__name__}")
client = tracking.init_weave(session["wandb_entity"], session["wandb_project"])
run_ids = {r["id"] for r in runs}
calls = [c for c in client.get_calls() if (getattr(c, "wb_run_id", "") or "").split("/")[-1] in run_ids]
ops = {}
for c in calls:
    op = c.op_name.split("/")[-1].split(":")[0]
    ops[op] = ops.get(op, 0) + 1
    if c.exception:
        problems.append(f"weave call {op} failed: {c.exception[:100]}")
for op in ('execute_training','evaluate_result','publish_research_state'):
    if ops.get(op,0) < len(runs):
        problems.append(f'Missing required {op} spans')
if session.get('protocol',{}).get('trace_link_version',0) >= 2 and session.get('final_decision'):
    for op,minimum in [('receive_aria_output',len(runs)),('record_aria_decision',len(runs)),('validate_experiment',len(runs)-1)]:
        if ops.get(op,0) < minimum:
            problems.append(f'Missing linked ARIA span: {op}')
final = session.get('final_evaluation')
if final:
    r = api.run(f"{project}/{final['wandb_run_url'].rsplit('/',1)[-1]}")
    value = float(r.summary.get('mean_test_auprc',float('nan')))
    if r.state != 'finished' or not math.isfinite(value) or abs(value-final['mean_test_auprc']) > 1e-12:
        problems.append('Final evaluation run does not match')
    try:
        a = api.artifact(f'{project}/{args.session}-final-evaluation:v0')
        root = Path(a.download(root=str(config.ARTIFACTS_DIR/'verification'/args.session)))
        if json.loads((root/'final_evaluation.json').read_text()) != final:
            problems.append('Final evaluation artifact content differs')
    except Exception as exc:
        problems.append(f'Final evaluation artifact failed: {type(exc).__name__}')
print(json.dumps({"session": args.session, "status": session["status"], "runs": runs, "artifacts": artifacts, "weave_calls_by_op": ops, "problems": problems}, indent=2))
sys.exit(1 if problems else 0)
