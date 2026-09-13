"""Build the ARIA exchange dataset from recorded sessions and run the Weave Evaluation.

  python scripts/run_agent_evals.py                 # all sessions with accepted ARIA messages
  python scripts/run_agent_evals.py --session ID    # one session
  python scripts/run_agent_evals.py --local-only    # scorecard only, no Weave publish
  python scripts/run_agent_evals.py --llm-judge     # add the W&B Inference hypothesis judge
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wildfire_researcher import agent_evals, config  # noqa: E402
from wildfire_researcher.state import Store  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--session", action="append", default=None)
parser.add_argument("--local-only", action="store_true")
parser.add_argument("--llm-judge", action="store_true")
parser.add_argument("--name", default=None)
args = parser.parse_args()

store = Store()
sessions = args.session or [s["id"] for s in store.list_sessions() if any(m["direction"] == "inbound" and m["accepted"] for m in store.aria_messages(s["id"]))]
fetch = agent_evals.wandb_state_fetcher(config.WANDB_ENTITY, config.WANDB_PROJECT, config.ARTIFACTS_DIR / "agent-evals" / "states")
rows = []
for sid in sessions:
    r = agent_evals.build_rows(store, sid, fetch)
    print(f"{sid}: {len(r)} exchanges", flush=True)
    rows.extend(r)
scored = agent_evals.score_rows(rows, with_llm_judge=args.llm_judge)
card = agent_evals.scorecard(scored)
per_session = {sid: agent_evals.scorecard([s for s in scored if s["session_id"] == sid]) for sid in sessions}
out_dir = config.ARTIFACTS_DIR / "agent-evals"
out_dir.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
(out_dir / f"scorecard-{stamp}.json").write_text(json.dumps({"overall": card, "per_session": per_session, "rows": scored}, indent=2), encoding="utf-8")
print(json.dumps({"overall": card, "per_session": per_session}, indent=2))
flagged = [s for s in scored if s["contract"]["valid"] is False or s["one_change"]["one_change"] is False or s["decision"]["consistent"] is False or (s["grounded"]["grounded_fraction"] is not None and s["grounded"]["grounded_fraction"] < 1)]
for s in flagged:
    print("FLAG", s["id"], {"contract": s["contract"], "one_change": s["one_change"]["changed"], "decision": s["decision"], "ungrounded": s["grounded"]["ungrounded"]})
if not args.local_only:
    name = args.name or f"aria-agent-eval-{stamp}"
    result = agent_evals.run_weave_evaluation(rows, entity=config.WANDB_ENTITY, project=config.WANDB_PROJECT, name=name, with_llm_judge=args.llm_judge)
    print("WEAVE EVALUATION", name, json.dumps(result, default=str)[:2000])
    print(f"open: https://wandb.ai/{config.WANDB_ENTITY}/{config.WANDB_PROJECT}/weave/evaluations")
