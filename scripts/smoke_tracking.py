"""Network smoke test: one W&B run + Weave op + state artifact in the real project (no training)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wildfire_researcher import config, tracking  # noqa: E402
from wildfire_researcher.aria_client import ARIAClient  # noqa: E402

config.load_wandb_credential()
session_id = "wf-smoke-tracking"
client = tracking.init_weave(config.WANDB_ENTITY, config.WANDB_PROJECT)


@tracking.op("smoke_op")
def smoke_op(x: int) -> dict:
    return {"x": x, "ok": True}


aria = ARIAClient(config.WANDB_ENTITY, config.WANDB_PROJECT, session_id, config.ARTIFACTS_DIR / session_id / "aria")
with tracking.ExperimentRun(entity=config.WANDB_ENTITY, project=config.WANDB_PROJECT, session_id=session_id, experiment_id="smoke", iteration=0, run_kind="smoke", exp_config={"purpose": "tracking smoke", "benchmark_comparable": False}) as run:
    print("run url:", run.url)
    smoke_op(1)
    run.log({"validation_auprc": 0.0})
    info = aria.publish_state(run.run, {"session_id": session_id, "state_revision": 1, "status": "smoke", "history": []}, config.ARTIFACTS_DIR / session_id / "state.json")
    print("state artifact:", json.dumps(info))
# fetch it back
art = aria._fetch(aria.state_artifact_name(), "research-state")
print("fetched:", art.name, art.version, art.digest)
missing = aria._fetch("does-not-exist-xyz", "research-proposal")
print("missing artifact ->", missing)
calls = list(client.get_calls(limit=5))
print("weave calls visible:", len(calls), [c.op_name.split("/")[-1].split(":")[0] for c in calls])
