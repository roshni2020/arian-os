"""Command-line interface. The research loop runs independently of the UI.

  python -m wildfire_researcher.cli setup-data
  python -m wildfire_researcher.cli research --budget 15 [--session ID] [--aria-mode connected|fallback]
  python -m wildfire_researcher.cli resume --session ID
  python -m wildfire_researcher.cli status --session ID
  python -m wildfire_researcher.cli automation-prompt --session ID
  python -m wildfire_researcher.cli final-eval --session ID [--experiment exp-003]
  python -m wildfire_researcher.cli replay-export --session ID
  python -m wildfire_researcher.cli cancel --session ID
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from . import config, protocol
from .state import Store, research_state

CANONICAL_FILES = [
    "fire_events_natural_2016_2020.parquet",
    "master_features_natural_2016_2020.parquet",
    "gridmet_daily_event_features_natural_2016_2020.parquet",
    "gridmet_features_natural_2016_2020.parquet",
    "viirs_features_natural_2016_2020.parquet",
    "landfire_fuel_veg_features_natural_2016_2020.parquet",
    "topography_features_natural_2016_2020.parquet",
    "osm_access_features_natural_2016_2020.parquet",
    "population_features_natural_2016_2020.parquet",
    "feature_manifest_natural.json",
    "label_manifest_natural.json",
    "temporal_protocol_manifest_natural.json",
    "event_patch_manifest_375m_natural.json",
]


def banner(session: dict) -> None:
    print("Wildfire Autonomous Researcher (ARIA)")
    print(f"Published target: {protocol.PUBLISHED_TEST_AUPRC} test AUPRC | session {session['id']} | ARIA mode {session['aria_mode']} | budget {session['budget']}")


def cmd_setup_data(args) -> int:
    target = config.CANONICAL_DIR
    target.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/datasets/{protocol.DATASET_REPO}/resolve/{protocol.DATASET_REVISION}/data/canonical/raw_feature_tables/"
    for name in CANONICAL_FILES:
        dest = target / name
        if dest.exists() and not args.force:
            print(f"exists  {name}")
            continue
        print(f"download {name}", flush=True)
        urllib.request.urlretrieve(base + name, dest)
    (target.parent / "HF_REVISION.txt").write_text(f"{protocol.DATASET_REPO}@{protocol.DATASET_REVISION}\n")
    print("Building official tabular caches for metadata and all (others build on demand)...")
    for proto in ("metadata", "all"):
        print(" ", protocol.ensure_tabular_cache(proto, 5))
    return 0


def cmd_verify_data(args):
    from .integrity import verify_dataset, verified_cache
    print(json.dumps(verify_dataset(),indent=2))
    for name in ('metadata','all'):
        verified_cache(name,5)
    print('Pinned dataset and baseline/full caches verified')
    return 0


def _print_progress(store: Store, session_id: str) -> None:
    state = research_state(store, session_id)
    for row in state["history"]:
        print(f"\nExperiment {row['iteration']} [{row['experiment_id']}] {row['controller']}")
        if row["observation"]:
            print(f"  Observation: {row['observation'][:300]}")
        print(f"  Hypothesis: {row['hypothesis'][:300]}")
        print(f"  Model: {row['experiment']['model']} | features: {row['experiment']['feature_protocol']} | weather_days: {row['experiment']['weather_days']} | change: {row['change_summary']}")
        print(f"  Validation AUPRC: {row['score']:.4f}" + (f" (delta {row['delta_vs_previous_best']:+.4f} vs previous best)" if row["delta_vs_previous_best"] is not None else ""))
        if row["decision"]:
            print(f"  ARIA decision: {row['decision']} - {row['decision_reason'][:300]}")
        if row["next_question"]:
            print(f"  Next question: {row['next_question'][:300]}")
    best = state["current_best_validation_auprc"]
    print(f"\nBest validation AUPRC: {best:.4f} | status: {state['status']} | remaining budget: {state['remaining_budget']}" if best is not None else f"\nstatus: {state['status']}")


def cmd_research(args) -> int:
    from .loop import ResearchLoop, make_aria

    store = Store(args.db)
    mode = args.aria_mode or config.ARIA_MODE
    if mode == "connected":
        config.load_wandb_credential()
    if mode == "fallback":
        print("WARNING: ARIA_MODE=fallback uses a scripted development stub. This is NOT ARIA and must not be judged as the researcher.")
    session = store.create_session(session_id=args.session, budget=args.budget, aria_mode=mode, research_seed=protocol.RESEARCH_SEED, fast_mode=config.FAST_MODE, limit_train_samples=args.limit_train_samples, entity=config.WANDB_ENTITY, project=config.WANDB_PROJECT)
    banner(session)
    if mode == "connected":
        print("\nBefore the baseline run finishes, make sure the W&B Automation for this session exists (see AUTOMATION.md).")
        print(f"Run filter regex: ^{session['id']}-(exp-\\d+|control-r\\d+)$")
    tracking_enabled = mode == "connected" and not args.no_tracking
    loop = ResearchLoop(store, session["id"], make_aria(session, config.ARTIFACTS_DIR / session["id"] / "aria"), tracking_enabled=tracking_enabled, wait_seconds=args.wait_seconds)
    loop.run()
    _print_progress(store, session["id"])
    return 0


def cmd_resume(args) -> int:
    from .loop import ResearchLoop, make_aria

    store = Store(args.db)
    session = store.get_session(args.session)
    if session["aria_mode"] == "connected":
        config.load_wandb_credential()
    store.update_session(session["id"], cancel_requested=False, error=None)
    banner(session)
    loop = ResearchLoop(store, session["id"], make_aria(session, config.ARTIFACTS_DIR / session["id"] / "aria"), tracking_enabled=session["aria_mode"] == "connected" and not args.no_tracking, wait_seconds=args.wait_seconds)
    loop.run()
    _print_progress(store, session["id"])
    return 0


def cmd_status(args) -> int:
    store = Store(args.db)
    if not args.session:
        for s in store.list_sessions():
            print(f"{s['id']}  {s['status']:<26} mode={s['aria_mode']:<9} best={s['current_best_auprc']}")
        return 0
    banner(store.get_session(args.session))
    _print_progress(store, args.session)
    return 0


def cmd_cancel(args) -> int:
    store = Store(args.db)
    store.update_session(args.session, cancel_requested=True)
    store.log_event(args.session, "cancel_requested", "Cancellation requested")
    print("cancel requested; the worker stops at the next safe point")
    return 0


def cmd_automation_prompt(args) -> int:
    from .aria_client import automation_prompt

    store = Store(args.db)
    session = store.get_session(args.session)
    prompt = automation_prompt(session["id"], session["wandb_entity"], session["wandb_project"])
    print(f"# Automation: event = run status changes to finished; scope = project {session['wandb_project']}; run name regex: ^{session['id']}-(exp-\\d+|control-r\\d+)$")
    print(f"# Prompt ({len(prompt)} chars):\n")
    print(prompt)
    return 0


def cmd_final_eval(args) -> int:
    from .final_eval import evaluate_frozen, evaluation_view

    store = Store(args.db)
    session = store.get_session(args.session)
    exp_id = args.experiment or (session["final_decision"] or {}).get("recommended_final_experiment_id")
    if not exp_id:
        print("No experiment given and ARIA has not recommended one yet (session must be complete).", file=sys.stderr)
        return 2
    tracking_enabled = not args.no_tracking
    if tracking_enabled:
        config.load_wandb_credential()
    result = evaluation_view(evaluate_frozen(store, session["id"], exp_id, seeds=args.seeds, tracking_enabled=tracking_enabled))
    print(json.dumps({k: result[k] for k in ("experiment_id", "mean_test_auprc", "std_test_auprc", "published_test_auprc", "delta_vs_published", "protocol_matched", "benchmark_beaten", "seeds")}, indent=2))
    return 0


def cmd_replay_export(args) -> int:
    from .loop import replay_record

    store = Store(args.db)
    record = replay_record(store, args.session)
    out = Path(args.out or (config.ARTIFACTS_DIR / args.session / "replay.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, default=str))
    print(out)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wildfire_researcher")
    p.add_argument("--db", default=None, help="SQLite path (default data/researcher.sqlite)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser('verify-data').set_defaults(fn=cmd_verify_data)
    s = sub.add_parser("setup-data"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_setup_data)
    s = sub.add_parser("research"); s.add_argument("--budget", type=int, default=config.DEFAULT_BUDGET); s.add_argument("--session", default=None); s.add_argument("--aria-mode", choices=["connected", "fallback"], default=None); s.add_argument("--wait-seconds", type=int, default=config.ARIA_WAIT_SECONDS); s.add_argument("--limit-train-samples", type=int, default=None); s.add_argument("--no-tracking", action="store_true"); s.set_defaults(fn=cmd_research)
    s = sub.add_parser("resume"); s.add_argument("--session", required=True); s.add_argument("--wait-seconds", type=int, default=config.ARIA_WAIT_SECONDS); s.add_argument("--no-tracking", action="store_true"); s.set_defaults(fn=cmd_resume)
    s = sub.add_parser("status"); s.add_argument("--session", default=None); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("cancel"); s.add_argument("--session", required=True); s.set_defaults(fn=cmd_cancel)
    s = sub.add_parser("automation-prompt"); s.add_argument("--session", required=True); s.set_defaults(fn=cmd_automation_prompt)
    s = sub.add_parser("final-eval"); s.add_argument("--session", required=True); s.add_argument("--experiment", default=None); s.add_argument("--seeds", type=int, nargs="*", default=None); s.add_argument("--no-tracking", action="store_true"); s.set_defaults(fn=cmd_final_eval)
    s = sub.add_parser("replay-export"); s.add_argument("--session", required=True); s.add_argument("--out", default=None); s.set_defaults(fn=cmd_replay_export)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
