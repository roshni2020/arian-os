"""The research loop state machine.

OBSERVE -> HYPOTHESIZE -> DESIGN (ARIA) -> VALIDATE -> TRAIN -> EVALUATE -> KEEP/REJECT (ARIA) -> next.

This module executes and records. Every hypothesis, experiment choice and decision comes from
ARIA via ARIAClient (or, for development tests only, an explicitly labelled fallback stub).
"""
from __future__ import annotations

import json
import time
import traceback
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable

from . import config, experiments as ex, protocol, runner, tracking
from .aria_client import ARIAClient, ARIATimeout
from .experiments import ProposalError
from .state import Store, numeric_best, research_state
from .execution import exclusive, bounded


class NullRun:
    """Stand-in for a W&B run when tracking is disabled (offline tests)."""

    url = None
    id = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def log(self, *_a, **_k):
        pass

    def summary(self, *_a, **_k):
        pass

    def log_table(self, *_a, **_k):
        pass

    def log_pr_curve(self, *_a, **_k):
        pass

    def log_artifact(self, *_a, **_k):
        return None

    @property
    def run(self):
        return None


class ResearchLoop:
    def __init__(self, store: Store, session_id: str, aria, *, tracking_enabled: bool = True, wait_seconds: int | None = None, poll_seconds: int | None = None, log: Callable[[str], None] | None = None):
        self.store = store
        self.session_id = session_id
        self.aria = aria
        self.tracking_enabled = tracking_enabled
        self.wait_seconds = wait_seconds or config.ARIA_WAIT_SECONDS
        self.poll_seconds = poll_seconds or config.ARIA_POLL_SECONDS
        self._log = log or (lambda msg: print(msg, flush=True))
        self.session = store.get_session(session_id)
        self.artifact_dir = config.ARTIFACTS_DIR / session_id
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.rejections_at_revision = 0

    # ---- helpers ------------------------------------------------------------------------
    def say(self, kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.store.log_event(self.session_id, kind, message, payload)
        self._log(message)

    def refresh(self) -> dict[str, Any]:
        self.session = self.store.get_session(self.session_id)
        return self.session

    def cancelled(self) -> bool:
        return bool(self.refresh()["cancel_requested"])

    def aria_context(self):
        if not self.tracking_enabled:
            return nullcontext()
        session = self.refresh()
        completed = self.store.completed_experiments(self.session_id)
        run_id = completed[-1]['wandb_run_id'] if completed else None
        return tracking.research_context(session['wandb_entity'],session['wandb_project'],
                                        self.session_id,run_id,session['state_revision'])

    def _run_context(self, experiment_id: str, iteration: int, run_kind: str, exp_config: dict[str, Any]):
        if not self.tracking_enabled:
            return NullRun()
        return tracking.ExperimentRun(
            entity=self.session["wandb_entity"],
            project=self.session["wandb_project"],
            session_id=self.session_id,
            experiment_id=experiment_id,
            iteration=iteration,
            run_kind=run_kind,
            exp_config=exp_config,
            tags=[f"session:{self.session_id}", f"aria_mode:{self.session['aria_mode']}", "score_kind:VALIDATION_AUPRC"],
        )

    # ---- traced steps ------------------------------------------------------------------
    @tracking.op("receive_aria_output")
    def receive_aria_output(self, kind: str, payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
        """Records an artifact ARIA produced in its own environment. Provenance only; no fabricated reasoning."""
        return {
            "kind": kind,
            "artifact_ref": meta.get("artifact_ref"),
            "artifact_version": meta.get("artifact_version"),
            "artifact_digest": meta.get("artifact_digest"),
            "file_sha256": meta.get("file_sha256"),
            "artifact_metadata": meta.get("artifact_metadata"),
            "payload": payload,
            "provenance": "Produced by ARIA in W&B's environment via Automation. ARIA's internal steps are not traced here.",
        }

    @tracking.op("validate_experiment")
    def validate_experiment(self, proposal: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return ex.validate_proposal(proposal, state)

    @tracking.op("execute_training")
    def execute_training(self, experiment: dict[str, Any], seed: int, out_dir: str, limit_train_samples: int | None) -> dict[str, Any]:
        return bounded(runner.run_experiment, experiment, seed, Path(out_dir),
                       limit_train_samples=limit_train_samples, should_cancel=self.cancelled)

    @tracking.op("evaluate_result")
    def evaluate_result(self, experiment_id: str, result: dict[str, Any], previous_best: float | None) -> dict[str, Any]:
        score = float(result["validation_auprc"])
        delta = None if previous_best is None else score - previous_best
        return {
            "experiment_id": experiment_id,
            "score_kind": result["score_kind"],
            "validation_auprc": score,
            "previous_best": previous_best,
            "delta_vs_previous_best": delta,
            "improved_numeric_best": previous_best is None or score > previous_best,
            "benchmark_comparable": False,
            "target_test_auprc": config.TARGET_AUPRC,
        }

    @tracking.op("record_aria_decision")
    def record_aria_decision(self, experiment_id: str, decision: dict[str, Any], source: str | None) -> dict[str, Any]:
        self.store.update_experiment(
            self.session_id,
            experiment_id,
            decision=decision["decision"],
            decision_reason=decision["reason"],
            decision_learning=decision["learning"],
            next_question=decision.get("next_question"),
            decision_source=source,
        )
        return {"experiment_id": experiment_id, **decision, "source": source}

    @tracking.op("publish_research_state")
    def publish_research_state(self, run, reason: str) -> dict[str, Any]:
        revision = self.store.bump_revision(self.session_id)
        state = research_state(self.store, self.session_id)
        assert state["state_revision"] == revision
        state_path = self.artifact_dir / "state.json"
        tracking.write_json(state_path, state)
        info: dict[str, Any] = {"state_revision": revision, "reason": reason, "local_path": str(state_path)}
        if self.tracking_enabled and self.aria is not None and hasattr(self.aria, "publish_state") and getattr(run, "run", None) is not None:
            info.update(self.aria.publish_state(run.run, state, state_path))
        elif self.aria is not None and hasattr(self.aria, "publish_state_local"):
            self.aria.publish_state_local(state)
        self.store.record_aria_message(self.session_id, direction="outbound", kind="state", artifact_ref=info.get("artifact_ref"), artifact_digest=info.get("digest"), state_revision=revision, accepted=None, feedback=None, payload={"reason": reason, "status": state["status"], "history_len": len(state["history"])})
        self.say("state_published", f"Research state r{revision} published ({reason})", {"state_revision": revision, "artifact": info.get("artifact_ref")})
        return info

    # ---- experiment execution ----------------------------------------------------------
    def run_claimed_experiment(self, experiment: dict[str, Any], next_status: str) -> dict[str, Any]:
        """Train one claimed experiment inside a W&B run, publish state before the run finishes."""
        session = self.refresh()
        exp = experiment["experiment"]
        completed = self.store.completed_experiments(self.session_id)
        _, previous_best = numeric_best(completed)
        exp_config = tracking.experiment_config_payload(session, experiment, exp, previous_best)
        out_dir = self.artifact_dir / experiment["id"]
        self.store.update_experiment(self.session_id, experiment["id"], status="training")
        self.store.set_status(self.session_id, "training", f"Training {experiment['id']}: {exp['model']} on {exp['feature_protocol']} ({experiment['change_summary']})")
        try:
            with self._run_context(experiment["id"], experiment["iteration"], "experiment", exp_config) as run:
                self.store.update_experiment(self.session_id, experiment["id"], wandb_run_id=run.id, wandb_run_url=run.url, weave_trace_url=tracking.latest_trace_url(session["wandb_entity"], session["wandb_project"], run.id) if run.id else None)
                result = self.execute_training(exp, session["research_seed"], str(out_dir), session["limit_train_samples"])
                self.store.set_status(self.session_id, "evaluating", f"Evaluating {experiment['id']} on the official validation year")
                evaluation = self.evaluate_result(experiment["id"], result, previous_best)
                score = evaluation["validation_auprc"]
                run.log({"validation_auprc": score, "validation_auroc": result["validation_auroc"], "train_auprc": result["train_auprc"], "precision": result["validation_metrics"]["precision"], "recall": result["validation_metrics"]["recall"], "f1": result["validation_metrics"]["f1"], "false_negatives": result["false_negative_count"], "false_positives": result["false_positive_count"], "runtime_seconds": result["runtime_seconds"], "n_features": result["n_features"], "previous_best": previous_best if previous_best is not None else float("nan"), "score_delta": evaluation["delta_vs_previous_best"] if evaluation["delta_vs_previous_best"] is not None else float("nan"), "target_test_auprc": config.TARGET_AUPRC, "iteration": experiment["iteration"]})
                run.log_pr_curve(result["pr_curve"])
                if result["feature_importance"]:
                    run.log_table("feature_importance", ["feature", "importance", "kind"], [[f["feature"], f["importance"], f["kind"]] for f in result["feature_importance"]])
                run.log_table("confusion_matrix", ["tp", "fp", "fn", "tn"], [[result["confusion_matrix"][k] for k in ("tp", "fp", "fn", "tn")]])
                run.summary({"score_kind": result["score_kind"], "benchmark_comparable": False, "experiment_id": experiment["id"], "session_id": self.session_id})
                self.store.update_experiment(self.session_id, experiment["id"], status="complete", result=result, score=score, previous_best=previous_best, delta=evaluation["delta_vs_previous_best"], runtime_seconds=result["runtime_seconds"])
                best_id, best = numeric_best(self.store.experiments(self.session_id))
                self.store.update_session(self.session_id, current_best_experiment_id=best_id, current_best_auprc=best)
                self.say("experiment_complete", f"{experiment['id']} validation AUPRC {score:.4f}" + (f" (delta {evaluation['delta_vs_previous_best']:+.4f} vs best)" if evaluation["delta_vs_previous_best"] is not None else " (baseline)"), {"experiment_id": experiment["id"], "score": score, "delta": evaluation["delta_vs_previous_best"]})
                self.store.set_status(self.session_id, next_status)
                info = self.publish_research_state(run, f"after {experiment['id']}")
                pred_path = Path(result["predictions_path"])
                if pred_path.exists():
                    run.log_artifact(f"{self.session_id}-{experiment['id']}-predictions", "predictions", {"predictions_val.npz": pred_path}, metadata={"experiment_id": experiment["id"], "split": "val"})
                if result.get('model_bundle_path'):
                    bundle = Path(result['model_bundle_path'])
                    run.log_artifact(f"{self.session_id}-{experiment['id']}-model", 'model',
                                     {p.name:p for p in bundle.iterdir() if p.is_file()},
                                     metadata={'session_id': self.session_id, 'experiment_id': experiment['id'],
                                               'validation_auprc':score, 'test_evaluated':False},
                                     aliases=['validation-candidate'])
                return {"result": result, "evaluation": evaluation, "state": info}
        except InterruptedError:
            self.store.update_experiment(self.session_id, experiment['id'], status='claimed')
            raise ARIATimeout('cancelled during training')
        except Exception as exc:
            self.store.update_experiment(self.session_id, experiment["id"], status="failed", error=f"{type(exc).__name__}: {exc}")
            self.say("experiment_failed", f"{experiment['id']} failed: {type(exc).__name__}: {exc}", {"experiment_id": experiment["id"], "traceback": traceback.format_exc()[-4000:]})
            raise

    def run_baseline(self) -> dict[str, Any]:
        exp = ex.canonical_experiment(ex.BASELINE_EXPERIMENT)
        key = ex.config_key(exp, self.session["research_seed"])
        claimed = self.store.claim_experiment(self.session_id, experiment=exp, config_key=key, controller="baseline_setup", proposal=None, proposal_source=None, parent_experiment_id=None, change_summary="baseline")
        self.store.set_status(self.session_id, "running_baseline", "Running fixed metadata-only logistic regression baseline")
        return self.run_claimed_experiment(claimed, "awaiting_aria_proposal")

    # ---- ARIA exchange -----------------------------------------------------------------
    def publish_feedback_state(self, reason: str) -> None:
        """Publish a new state revision through a control run so ARIA is re-invoked with feedback."""
        session = self.refresh()
        rev = session["state_revision"] + 1
        with self._run_context(f"control-r{rev}", -1, f"control-r{rev}", {"controller": "worker", "purpose": reason, "benchmark_comparable": False, "session_id": self.session_id}) as run:
            self.publish_research_state(run, reason)
        if self.tracking_enabled:
            completed = self.store.completed_experiments(self.session_id)
            if completed:
                tracking.init_weave(session['wandb_entity'],session['wandb_project']).set_wandb_run_context(run_id=completed[-1]['wandb_run_id'])

    def _wait_with_nudges(self, kind: str, rev: int) -> tuple[dict[str, Any], dict[str, Any]]:
        """Wait for ARIA's artifact. If nothing arrives within ARIA_NUDGE_SECONDS, re-publish the state
        through a control run (a fresh run-finished event) and wait for the new revision, up to
        ARIA_MAX_NUDGES times; then give up with ARIATimeout. Never chooses an experiment itself."""
        nudges = 0
        total_deadline = time.monotonic() + self.wait_seconds
        while True:
            remaining = max(1, int(total_deadline - time.monotonic()))
            window = min(config.ARIA_NUDGE_SECONDS, remaining) if nudges < config.ARIA_MAX_NUDGES else remaining
            try:
                return self.aria.wait_for(kind, rev, wait_seconds=window, poll_seconds=self.poll_seconds, should_cancel=self.cancelled, on_tick=lambda w: self.say("waiting", f"Still waiting for ARIA ({kind}, r{rev}, {w}s)") if w and w % 120 == 0 else None)
            except ARIATimeout:
                if self.cancelled() or nudges >= config.ARIA_MAX_NUDGES or time.monotonic() >= total_deadline:
                    raise
                nudges += 1
                self.say("aria_nudge", f"No ARIA {kind} for r{rev} after {window}s; re-publishing state through a control run (nudge {nudges}/{config.ARIA_MAX_NUDGES})", {"revision": rev, "nudge": nudges})
                self.publish_feedback_state(f"no ARIA response for r{rev}; nudge {nudges}")
                if self.tracking_enabled:
                    previous = self.store.completed_experiments(self.session_id)[-1]
                    tracking.init_weave(self.session['wandb_entity'], self.session['wandb_project']).set_wandb_run_context(run_id=previous['wandb_run_id'])
                rev = self.refresh()["state_revision"]

    def await_proposal(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Wait for a valid proposal for the current revision. Returns (validated, raw, meta)."""
        while True:
            if self.cancelled():
                raise ARIATimeout("cancelled")
            session = self.refresh()
            rev = session["state_revision"]
            self.store.set_status(self.session_id, "awaiting_aria_proposal", f"Waiting for ARIA proposal for state revision r{rev}")
            raw, meta = self._wait_with_nudges("proposal", rev)
            rev = self.refresh()["state_revision"]  # a nudge may have advanced the revision ARIA answered
            self.receive_aria_output("proposal", raw, meta)
            self.store.set_status(self.session_id, "validating_proposal", f"Validating ARIA proposal from {meta.get('artifact_ref')}")
            state = research_state(self.store, self.session_id)
            try:
                validated = self.validate_experiment(raw, state)
            except ProposalError as err:
                self.rejections_at_revision += 1
                self.store.record_aria_message(self.session_id, direction="inbound", kind="proposal", artifact_ref=meta.get("artifact_ref"), artifact_digest=meta.get("artifact_digest"), state_revision=rev, accepted=False, feedback=err.feedback(), payload=raw)
                self.say("proposal_rejected", f"ARIA proposal rejected ({err.code}): {err.message}", {"feedback": err.feedback(), "artifact": meta.get("artifact_ref")})
                if self.rejections_at_revision >= config.ARIA_MAX_REJECTIONS:
                    raise RuntimeError(f"ARIA produced {self.rejections_at_revision} invalid proposals in a row; stopping without choosing an experiment myself")
                self.publish_feedback_state(f"rejected proposal: {err.code}")
                continue
            self.rejections_at_revision = 0
            self.store.record_aria_message(self.session_id, direction="inbound", kind="proposal", artifact_ref=meta.get("artifact_ref"), artifact_digest=meta.get("artifact_digest"), state_revision=rev, accepted=True, feedback=None, payload=raw)
            return validated, raw, meta

    def await_final_decision(self) -> dict[str, Any]:
        while True:
            if self.cancelled():
                raise ARIATimeout("cancelled")
            session = self.refresh()
            rev = session["state_revision"]
            self.store.set_status(self.session_id, "awaiting_final_decision", f"Budget exhausted; waiting for ARIA final decision (r{rev})")
            raw, meta = self._wait_with_nudges("decision", rev)
            rev = self.refresh()["state_revision"]
            self.receive_aria_output("decision", raw, meta)
            state = research_state(self.store, self.session_id)
            try:
                decision = ex.validate_final_decision(raw, state)
            except ProposalError as err:
                self.rejections_at_revision += 1
                self.store.record_aria_message(self.session_id, direction="inbound", kind="decision", artifact_ref=meta.get("artifact_ref"), artifact_digest=meta.get("artifact_digest"), state_revision=rev, accepted=False, feedback=err.feedback(), payload=raw)
                self.say("decision_rejected", f"ARIA final decision rejected ({err.code}): {err.message}", {"feedback": err.feedback()})
                if self.rejections_at_revision >= config.ARIA_MAX_REJECTIONS:
                    raise RuntimeError("ARIA produced repeated invalid final decisions")
                self.publish_feedback_state(f"rejected final decision: {err.code}")
                continue
            self.store.record_aria_message(self.session_id, direction="inbound", kind="decision", artifact_ref=meta.get("artifact_ref"), artifact_digest=meta.get("artifact_digest"), state_revision=rev, accepted=True, feedback=None, payload=raw)
            last = self.store.completed_experiments(self.session_id)[-1]
            self.record_aria_decision(last["id"], decision, meta.get("artifact_ref"))
            final = {**decision, "source": meta.get("artifact_ref"), "artifact_digest": meta.get("artifact_digest")}
            self.store.update_session(self.session_id, final_decision=final)
            self.say("final_decision", f"ARIA final decision for {last['id']}: {decision['decision']}; recommends {decision['recommended_final_experiment_id']} for official evaluation", final)
            return final

    # ---- main entry --------------------------------------------------------------------
    @exclusive
    def run(self) -> dict[str, Any]:
        session = self.refresh()
        if session["status"] == "complete":
            self.say("info", "Session already complete")
            return session
        if session["status"] in {"cancelled", "error"}:
            self.store.update_session(self.session_id, cancel_requested=False, error=None)
            self.say("resume", f"Resuming session from status {session['status']}")
        try:
            unfinished = self.store.unfinished_experiment(self.session_id)
            if unfinished:
                # Recovery: a claimed/training experiment was interrupted. Re-run it; its configuration is durable.
                self.say("recovery", f"Recovering interrupted {unfinished['id']} ({unfinished['status']})")
                self.run_claimed_experiment(unfinished, "awaiting_aria_proposal")
            elif not self.store.completed_experiments(self.session_id):
                self.run_baseline()
            while True:
                if self.cancelled():
                    self.store.set_status(self.session_id, "cancelled", "Cancelled by user; state preserved")
                    return self.refresh()
                state = research_state(self.store, self.session_id)
                if state["remaining_budget"] <= 0:
                    with self.aria_context():
                        self.await_final_decision()
                    self.store.set_status(self.session_id, "complete", "Research loop complete. Run final-eval to freeze and score the recommended configuration on the official test year.")
                    with self._run_context("final-decision", -1, "final-decision", {"controller": "worker", "benchmark_comparable": False, "session_id": self.session_id}) as run:
                        self.publish_research_state(run, "complete")
                    return self.refresh()
                with self.aria_context():
                    validated, raw, meta = self.await_proposal()
                    last = self.store.completed_experiments(self.session_id)[-1]
                    self.record_aria_decision(last["id"], validated["previous_decision"], meta.get("artifact_ref"))
                self.say("aria_decision", f"ARIA {validated['previous_decision']['decision']} {last['id']}: {validated['previous_decision']['reason'][:200]}", validated["previous_decision"])
                change = change_summary(self.store.completed_experiments(self.session_id), validated["experiment"])
                claimed = self.store.claim_experiment(self.session_id, experiment=validated["experiment"], config_key=validated["config_key"], controller="ARIA", proposal={k: validated[k] for k in ("proposal_id", "observation", "hypothesis", "expected_result", "reason")} | {"raw": raw, "artifact": meta}, proposal_source=meta.get("artifact_ref"), parent_experiment_id=last["id"], change_summary=change)
                self.say("aria_proposal", f"ARIA proposes {claimed['id']}: {validated['hypothesis'][:200]}", {"experiment_id": claimed["id"], "hypothesis": validated["hypothesis"], "observation": validated["observation"], "change": change})
                self.run_claimed_experiment(claimed, "awaiting_aria_proposal")
        except ARIATimeout as exc:
            if self.cancelled():
                self.store.set_status(self.session_id, "cancelled", "Cancelled by user; state preserved")
            else:
                self.store.update_session(self.session_id, error=str(exc))
                self.store.set_status(self.session_id, "error", f"ARIA did not respond: {exc}. No fallback experiment was executed; resume when ARIA responds.")
            return self.refresh()
        except Exception as exc:
            self.store.update_session(self.session_id, error=f"{type(exc).__name__}: {exc}")
            self.store.set_status(self.session_id, "error", f"Loop error: {type(exc).__name__}: {exc}")
            self.say("traceback", traceback.format_exc()[-4000:])
            return self.refresh()


def change_summary(completed: list[dict[str, Any]], new_experiment: dict[str, Any]) -> str:
    """Describe the new experiment relative to the previous one, or to the incumbent numeric best
    when that is a shorter description (ARIA often reverts to the best and changes one thing)."""
    if not completed:
        return "baseline"
    last = completed[-1]
    vs_last = ex.describe_change(last["experiment"], new_experiment)
    best_id, _ = numeric_best(completed)
    best = next((e for e in completed if e["id"] == best_id), last)
    vs_best = ex.describe_change(best["experiment"], new_experiment)
    if best["id"] != last["id"] and len(vs_best) < len(vs_last):
        return ", ".join(vs_best) + f" (vs best {best['id']})"
    return ", ".join(vs_last)


def make_aria(session: dict[str, Any], download_root: Path):
    mode = session["aria_mode"]
    if mode == "connected":
        return ARIAClient(session["wandb_entity"], session["wandb_project"], session["id"], download_root)
    if mode == "fallback":
        from .fallback import FallbackARIA

        return FallbackARIA(session["id"], download_root)
    raise ValueError(f"No ARIA client for mode {mode}; replay mode never runs the loop")


def replay_record(store: Store, session_id: str) -> dict[str, Any]:
    """Export the complete verified record of a session for replay. No retraining, no ARIA calls."""
    session = store.get_session(session_id)
    from .api import _dataset_context
    return {
        "replay_format": 1,
        "exported_at": research_state(store, session_id)["generated_at"],
        "session": session,
        "state": research_state(store, session_id),
        "experiments": store.experiments(session_id),
        "events": store.events(session_id, 0, 5000),
        "aria_messages": store.aria_messages(session_id),
        'dataset':_dataset_context(),
    }
