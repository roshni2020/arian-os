"""Weave Evaluations of ARIA as a researcher.

The unit under evaluation is one real exchange: the research state ARIA was given (fetched from
the versioned `<session>-state:r<N>` artifact it actually read) and the proposal or final decision
it published. Nothing is re-generated: the "model" replays recorded outputs, so every score is a
judgement of what ARIA really did, and re-running the evaluation after a prompt or validator change
is a regression test of the loop.

Deterministic scorers (no LLM needed):
  contract        - passes the strict validator that the worker applies live
  one_change      - exactly one variable changed versus the incumbent best (or a declared revert)
  grounded        - numbers cited in ARIA's observation appear in the state it was given
  decision        - KEEP/REJECT agrees with the measured delta; flags decisions inside seed noise
  prediction      - ARIA's stated expected result versus the measured outcome of that experiment
  novelty         - the proposed configuration had not been run before
Optional LLM judge (W&B Inference, opt-in): hypothesis is falsifiable and follows from the observation.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Callable

from . import config, experiments as ex, protocol
from .state import Store

SEED_NOISE_AUPRC = 0.003  # observed seed-to-seed std of validation AUPRC is ~0.002-0.0024
NUMBER_RE = re.compile(r"(?<![\w.])(\d+\.\d{2,}|\d{2,})(?![\w.])")


# ---------------------------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------------------------

def compact_state(state: dict[str, Any]) -> dict[str, Any]:
    """The subset of the state the scorers and validator need (keeps rows small)."""
    history = []
    for h in state.get("history", []):
        history.append({
            "experiment_id": h["experiment_id"],
            "iteration": h.get("iteration"),
            "config_key": h.get("config_key"),
            "experiment": h["experiment"],
            "score": h.get("score"),
            "delta_vs_previous_best": h.get("delta_vs_previous_best"),
            "decision": h.get("decision"),
        })
    return {
        "session_id": state["session_id"],
        "state_revision": state["state_revision"],
        "research_seed": state.get("research_seed", protocol.RESEARCH_SEED),
        "remaining_budget": state.get("remaining_budget", 0),
        "budget": state.get("budget"),
        "numeric_best": state.get("numeric_best"),
        "awaiting_decision_for_experiment_id": state.get("awaiting_decision_for_experiment_id"),
        "seen_proposal_ids": list(state.get("seen_proposal_ids", [])),
        "history": history,
    }


# Parts of the state that are configuration or contract text, not measurements. Numbers there
# (hyperparameter defaults, bounds, budgets) must not make a cited "measurement" look grounded.
NON_MEASUREMENT_KEYS = {"capabilities", "protocol", "objective", "instructions", "allowed", "provenance", "experiment", "hyperparameters", "seen_proposal_ids", "config_key", "schema_version", "state_revision", "budget", "remaining_budget", "research_seed", "generated_at", "wandb_run_url", "weave_trace_url", "runtime_seconds", "seed"}


def state_numbers(state: dict[str, Any]) -> list[float]:
    """Every measured number in the state ARIA saw (scores, counts, breakdowns, importances)."""
    found: set[float] = set()

    def walk(v: Any) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)) and math.isfinite(v):
            found.add(float(v))
        elif isinstance(v, str):
            for m in NUMBER_RE.findall(v):
                try:
                    found.add(float(m))
                except ValueError:
                    pass
        elif isinstance(v, dict):
            for k, x in v.items():
                if k not in NON_MEASUREMENT_KEYS:
                    walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(state)
    return sorted(found)


def _exp_summary(e: dict[str, Any] | None) -> dict[str, Any] | None:
    if not e:
        return None
    return {"experiment_id": e["id"], "score": e["score"], "delta_vs_previous_best": e["delta"], "previous_best": e["previous_best"], "experiment": e["experiment"]}


def build_rows(store: Store, session_id: str, fetch_state: Callable[[str, int], dict[str, Any] | None]) -> list[dict[str, Any]]:
    """One row per accepted inbound ARIA message. `fetch_state(session, revision)` returns the state
    ARIA read for that revision (None if unavailable; such exchanges are skipped)."""
    exps = store.completed_experiments(session_id)
    by_id = {e["id"]: e for e in exps}
    by_proposal_id = {}
    for e in exps:
        pid = (e.get("proposal") or {}).get("proposal_id")
        if pid:
            by_proposal_id[pid] = e
    rows = []
    for m in store.aria_messages(session_id):
        if m["direction"] != "inbound" or not m["accepted"] or not isinstance(m["payload"], dict):
            continue
        payload = m["payload"]
        revision = payload.get("state_revision") if isinstance(payload.get("state_revision"), int) else m["state_revision"]
        state = fetch_state(session_id, revision)
        if state is None:
            continue
        kind = m["kind"]
        decided_id = (payload.get("previous_decision") or {}).get("experiment_id") if kind == "proposal" else payload.get("experiment_id")
        rows.append({
            "id": f"{session_id}-r{revision}-{kind}",
            "session_id": session_id,
            "kind": kind,
            "state_revision": revision,
            "artifact_ref": m["artifact_ref"],
            "state": compact_state(state),
            "state_numbers": state_numbers(state),
            "aria_output": payload,
            "resulting": _exp_summary(by_proposal_id.get(payload.get("proposal_id"))) if kind == "proposal" else None,
            "decided": _exp_summary(by_id.get(decided_id)) if decided_id else None,
        })
    return rows


def wandb_state_fetcher(entity: str, project: str, cache_dir: Path) -> Callable[[str, int], dict[str, Any] | None]:
    """Fetch `<session>-state:r<N>` from W&B (cached on disk)."""
    config.load_wandb_credential()
    import wandb

    api = wandb.Api()

    def fetch(session_id: str, revision: int) -> dict[str, Any] | None:
        path = cache_dir / session_id / f"state-r{revision}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        try:
            art = api.artifact(f"{entity}/{project}/{session_id}-state:r{revision}", type="research-state")
            root = Path(art.download(root=str(cache_dir / session_id / f"dl-r{revision}")))
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        except Exception:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
        return state

    return fetch


# ---------------------------------------------------------------------------------------------
# Scorers (pure functions; wrapped as Weave ops at evaluation time)
# ---------------------------------------------------------------------------------------------

def score_contract(kind: str, state: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    try:
        if kind == "proposal":
            ex.validate_proposal(output, state)
        else:
            ex.validate_final_decision(output, state)
        return {"valid": True, "code": None}
    except ex.ProposalError as err:
        return {"valid": False, "code": err.code}
    except Exception as err:  # noqa: BLE001
        return {"valid": False, "code": f"error:{type(err).__name__}"}


def _incumbent(state: dict[str, Any]) -> dict[str, Any] | None:
    best_id = (state.get("numeric_best") or {}).get("experiment_id")
    for h in state.get("history", []):
        if h["experiment_id"] == best_id:
            return h
    return state["history"][-1] if state.get("history") else None


def score_one_change(kind: str, state: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    if kind != "proposal":
        return {"one_change": None, "changes": None, "changed": None}
    try:
        new = ex.canonical_experiment(output.get("experiment"))
    except ex.ProposalError:
        return {"one_change": False, "changes": None, "changed": None}
    inc = _incumbent(state)
    if inc is None:
        return {"one_change": True, "changes": 0, "changed": ["baseline"]}
    changes = ex.describe_change(inc["experiment"], new)
    changed = [] if changes == ["no change"] else changes
    return {"one_change": len(changed) == 1, "changes": len(changed), "changed": changed}


def _derived_pool(values: list[float]) -> tuple[list[float], list[float]]:
    """State numbers plus pairwise differences (ARIA reports deltas and gaps it computed itself).
    Floats in [0, 1] (scores, rates) and integers (counts) are combined separately."""
    import numpy as np

    scores = np.array([v for v in values if 0.0 <= v <= 1.0 and not float(v).is_integer()], dtype=float)
    counts = np.array([v for v in values if float(v).is_integer() and abs(v) < 1e7], dtype=float)
    derived: list[float] = []
    for arr in (scores[:2500], counts[:2500]):
        if len(arr) > 1:
            diff = np.abs(arr[:, None] - arr[None, :])
            derived.extend(np.unique(diff).tolist())
    return list(values), derived


def score_grounded(output: dict[str, Any], state_numbers: list[float]) -> dict[str, Any]:
    """Fraction of numbers ARIA cites as facts (observation, decision reason/learning) that exist in
    the state it saw or are a difference of two such numbers. Targets in hypothesis/expected_result
    are ARIA's own predictions and are scored by `score_prediction` instead."""
    parts = [str(output.get("observation", "")), str(output.get("reason", "")) if "experiment" not in output else "", str(output.get("learning", ""))]
    block = output.get("previous_decision")
    if isinstance(block, dict):
        parts += [str(block.get("reason", "")), str(block.get("learning", ""))]
    text = " ".join(parts)
    cited = NUMBER_RE.findall(text)
    if not cited:
        return {"grounded_fraction": None, "cited": 0, "ungrounded": [], "derived": 0}
    direct, derived = _derived_pool(state_numbers)
    ungrounded, n_derived = [], 0
    for c in cited:
        value = float(c)
        decimals = len(c.split(".")[1]) if "." in c else 0
        target = round(value, decimals)
        if any(round(x, decimals) == target for x in direct):
            continue
        if any(round(x, decimals) == target for x in derived):
            n_derived += 1
            continue
        ungrounded.append(c)
    return {"grounded_fraction": 1 - len(ungrounded) / len(cited), "cited": len(cited), "ungrounded": ungrounded[:10], "derived": n_derived}


def score_decision(kind: str, output: dict[str, Any], decided: dict[str, Any] | None) -> dict[str, Any]:
    block = output.get("previous_decision") if kind == "proposal" else output
    decision = (block or {}).get("decision")
    if decision not in ("KEEP", "REJECT") or not decided:
        return {"consistent": None, "within_noise": None, "delta": None, "decision": decision}
    delta = decided.get("delta_vs_previous_best")
    if delta is None:  # baseline: nothing to compare with, any decision is a reference decision
        return {"consistent": True, "within_noise": None, "delta": None, "decision": decision}
    expected = "KEEP" if delta >= 0 else "REJECT"
    return {"consistent": decision == expected, "within_noise": abs(delta) < SEED_NOISE_AUPRC, "delta": delta, "decision": decision}


_TARGET_RE = re.compile(r"(?:above|at least|to at least|exceed(?:s|ing)?|>=|≥|over|beyond|reach(?:es|ing)?)\s*(0\.\d{2,})")


def score_prediction(kind: str, output: dict[str, Any], resulting: dict[str, Any] | None) -> dict[str, Any]:
    """Did the experiment do what ARIA said it would? Direction (improve vs best) and any numeric target."""
    if kind != "proposal" or not resulting or resulting.get("score") is None:
        return {"direction_hit": None, "target": None, "target_hit": None}
    delta = resulting.get("delta_vs_previous_best")
    direction_hit = None if delta is None else delta > 0
    m = _TARGET_RE.search(str(output.get("expected_result", ""))) or _TARGET_RE.search(str(output.get("hypothesis", "")))
    target = float(m.group(1)) if m else None
    target_hit = None if target is None else resulting["score"] >= target
    return {"direction_hit": direction_hit, "target": target, "target_hit": target_hit, "measured": resulting["score"]}


def score_novelty(kind: str, state: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    if kind != "proposal":
        return {"novel": None}
    try:
        new = ex.canonical_experiment(output.get("experiment"))
    except ex.ProposalError:
        return {"novel": False}
    key = ex.config_key(new, state.get("research_seed", protocol.RESEARCH_SEED))
    return {"novel": all(h.get("config_key") != key for h in state.get("history", []))}


def llm_judge(output: dict[str, Any], kind: str, model: str = "openai/gpt-oss-120b") -> dict[str, Any]:
    """Optional: W&B Inference (OpenAI-compatible) judges hypothesis quality. Returns None scores on failure."""
    if kind != "proposal":
        return {"falsifiable": None, "follows_from_observation": None, "judge_error": None}
    import httpx

    prompt = (
        "You are reviewing one step of an autonomous ML research agent. Answer with JSON only: "
        '{"falsifiable": true|false, "follows_from_observation": true|false, "note": "<=20 words"}.\n'
        "falsifiable: the hypothesis names a measurable outcome that could fail.\n"
        "follows_from_observation: the hypothesis is a reasonable response to the observation's evidence.\n\n"
        f"OBSERVATION: {output.get('observation', '')}\n\nHYPOTHESIS: {output.get('hypothesis', '')}\n\nEXPECTED: {output.get('expected_result', '')}"
    )
    try:
        content, match = "", None
        for attempt in range(2):  # reasoning models sometimes spend the whole budget thinking; retry once
            r = httpx.post(
                "https://api.inference.wandb.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {config_key()}", "OpenAI-Project": f"{config.WANDB_ENTITY}/{config.WANDB_PROJECT}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": 1200, "reasoning_effort": "low"},
                timeout=90,
            )
            r.raise_for_status()
            message = r.json()["choices"][0]["message"]
            content = (message.get("content") or "") + " " + (message.get("reasoning_content") or "")
            match = re.search(r"\{[^{}]*\}", content, re.S)
            if match:
                break
        if not match:
            return {"falsifiable": None, "follows_from_observation": None, "judge_error": f"no JSON in judge reply: {content[:80]!r}"}
        data = json.loads(match.group(0))
        return {"falsifiable": bool(data.get("falsifiable")), "follows_from_observation": bool(data.get("follows_from_observation")), "judge_error": None, "note": data.get("note")}
    except Exception as err:  # noqa: BLE001
        return {"falsifiable": None, "follows_from_observation": None, "judge_error": f"{type(err).__name__}: {str(err)[:120]}"}


def config_key() -> str:
    import os

    config.load_wandb_credential()
    return os.environ["WANDB_API_KEY"]


# ---------------------------------------------------------------------------------------------
# Local scorecard (no Weave needed) and Weave evaluation
# ---------------------------------------------------------------------------------------------

def score_rows(rows: list[dict[str, Any]], with_llm_judge: bool = False) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        s = {
            "contract": score_contract(r["kind"], r["state"], r["aria_output"]),
            "one_change": score_one_change(r["kind"], r["state"], r["aria_output"]),
            "grounded": score_grounded(r["aria_output"], r["state_numbers"]),
            "decision": score_decision(r["kind"], r["aria_output"], r["decided"]),
            "prediction": score_prediction(r["kind"], r["aria_output"], r["resulting"]),
            "novelty": score_novelty(r["kind"], r["state"], r["aria_output"]),
        }
        if with_llm_judge:
            s["judge"] = llm_judge(r["aria_output"], r["kind"])
        out.append({"id": r["id"], "session_id": r["session_id"], "kind": r["kind"], **s})
    return out


def _rate(values: list[Any]) -> float | None:
    vals = [v for v in values if v is not None]
    return (sum(1 for v in vals if v) / len(vals)) if vals else None


def scorecard(scored: list[dict[str, Any]]) -> dict[str, Any]:
    proposals = [s for s in scored if s["kind"] == "proposal"]
    return {
        "exchanges": len(scored),
        "proposals": len(proposals),
        "contract_valid_rate": _rate([s["contract"]["valid"] for s in scored]),
        "one_change_rate": _rate([s["one_change"]["one_change"] for s in proposals]),
        "grounded_fraction_mean": (lambda v: sum(v) / len(v) if v else None)([s["grounded"]["grounded_fraction"] for s in scored if s["grounded"]["grounded_fraction"] is not None]),
        "decision_consistent_rate": _rate([s["decision"]["consistent"] for s in scored]),
        "decisions_within_seed_noise": sum(1 for s in scored if s["decision"]["within_noise"]),
        "prediction_direction_hit_rate": _rate([s["prediction"]["direction_hit"] for s in proposals]),
        "prediction_target_hit_rate": _rate([s["prediction"]["target_hit"] for s in proposals]),
        "novel_rate": _rate([s["novelty"]["novel"] for s in proposals]),
        "judge_falsifiable_rate": _rate([s.get("judge", {}).get("falsifiable") for s in proposals]) if any("judge" in s for s in scored) else None,
        "judge_follows_rate": _rate([s.get("judge", {}).get("follows_from_observation") for s in proposals]) if any("judge" in s for s in scored) else None,
    }


def run_weave_evaluation(rows: list[dict[str, Any]], *, entity: str, project: str, name: str, with_llm_judge: bool = False) -> dict[str, Any]:
    """Publish the dataset and run a Weave Evaluation over the recorded exchanges."""
    import asyncio

    import weave

    weave.init(f"{entity}/{project}")

    class RecordedARIA(weave.Model):
        """Replays what real ARIA published for each exchange; nothing is regenerated."""

        source: str = "W&B artifacts research-proposal / research-decision"

        @weave.op()
        def predict(self, aria_output: dict) -> dict:
            return aria_output

    @weave.op()
    def contract(kind: str, state: dict, output: dict) -> dict:
        return score_contract(kind, state, output)

    @weave.op()
    def one_change(kind: str, state: dict, output: dict) -> dict:
        return score_one_change(kind, state, output)

    @weave.op()
    def grounded(output: dict, state_numbers: list) -> dict:
        return score_grounded(output, state_numbers)

    @weave.op()
    def decision(kind: str, output: dict, decided: dict | None) -> dict:
        return score_decision(kind, output, decided)

    @weave.op()
    def prediction(kind: str, output: dict, resulting: dict | None) -> dict:
        return score_prediction(kind, output, resulting)

    @weave.op()
    def novelty(kind: str, state: dict, output: dict) -> dict:
        return score_novelty(kind, state, output)

    scorers = [contract, one_change, grounded, decision, prediction, novelty]
    if with_llm_judge:

        @weave.op()
        def hypothesis_judge(kind: str, output: dict) -> dict:
            return llm_judge(output, kind)

        scorers.append(hypothesis_judge)

    dataset = weave.Dataset(name="aria-research-exchanges", rows=rows)
    weave.publish(dataset)
    evaluation = weave.Evaluation(name=name, dataset=dataset, scorers=scorers, evaluation_name=name)
    result = asyncio.run(evaluation.evaluate(RecordedARIA()))
    return result
