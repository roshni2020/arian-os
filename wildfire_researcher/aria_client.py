"""ARIAClient: asynchronous research exchange with W&B's ARIA through W&B Artifacts.

Proven path (see aria_probe/RESULTS.md): the worker publishes `<session>-state` (type
research-state); a W&B Automation configured in the UI invokes ARIA when an experiment run
finishes; ARIA reads the state in its own environment and publishes
`<session>-proposal-r<revision>` (type research-proposal) or `<session>-decision-final`
(type research-decision). The worker waits for those artifacts, validates them, and continues.

There is no direct prompt-to-ARIA API in this path. Each event starts a NEW ARIA conversation,
so the complete state is sent every cycle. This module never chooses experiments.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from . import config
from .tracking import sha256_file

PROPOSAL_TYPE = "research-proposal"
DECISION_TYPE = "research-decision"
STATE_TYPE = "research-state"


class ARIATimeout(Exception):
    pass


class ARIAClient:
    def __init__(self, entity: str, project: str, session_id: str, download_root: Path, mode: str = "connected"):
        self.entity, self.project, self.session_id = entity, project, session_id
        self.download_root = Path(download_root)
        self.mode = mode
        self._api = None

    # ---- naming ------------------------------------------------------------------------
    def state_artifact_name(self) -> str:
        return f"{self.session_id}-state"

    def proposal_artifact_name(self, revision: int) -> str:
        return f"{self.session_id}-proposal-r{revision}"

    def final_decision_artifact_name(self) -> str:
        return f"{self.session_id}-decision-final"

    def qualified(self, name: str, alias: str = "latest") -> str:
        return f"{self.entity}/{self.project}/{name}:{alias}"

    # ---- W&B API -----------------------------------------------------------------------
    @property
    def api(self):
        if self._api is None:
            config.load_wandb_credential()
            import wandb

            self._api = wandb.Api()
        return self._api

    def _fetch(self, name: str, kind: str):
        import wandb

        try:
            return self.api.artifact(self.qualified(name), type=kind)
        except wandb.errors.CommError as exc:
            msg = str(exc).lower()
            if "not found" in msg or "does not exist" in msg or "unable to fetch" in msg:
                return None
            raise
        except Exception as exc:  # the SDK raises ValueError for some missing artifacts
            if "not found" in str(exc).lower() or "does not exist" in str(exc).lower():
                return None
            raise

    def _download(self, artifact, filename: str) -> tuple[dict[str, Any], dict[str, Any]]:
        target = self.download_root / artifact.name.replace(":", "_")
        root = Path(artifact.download(root=str(target)))
        path = root / filename
        if not path.exists():
            raise FileNotFoundError(f"Artifact {artifact.name} has no {filename}")
        text = path.read_text(encoding="utf-8")
        if len(text) > 200_000:
            raise ValueError("ARIA artifact file is unexpectedly large")
        payload = json.loads(text)
        meta = {
            "artifact_ref": f"{self.entity}/{self.project}/{artifact.name.rsplit(':',1)[0]}:{artifact.version}",
            "artifact_version": artifact.version,
            "artifact_digest": artifact.digest,
            "file_sha256": sha256_file(path),
            "artifact_metadata": dict(artifact.metadata or {}),
            "created_at": str(getattr(artifact, "created_at", "")),
            "local_path": str(path),
        }
        return payload, meta

    # ---- publishing state --------------------------------------------------------------
    def publish_state(self, run, state: dict[str, Any], state_path: Path) -> dict[str, Any]:
        """Log the state artifact from within an active W&B run; returns artifact reference metadata."""
        import wandb

        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, default=str))
        art = wandb.Artifact(
            self.state_artifact_name(),
            type=STATE_TYPE,
            metadata={"session_id": self.session_id, "state_revision": state["state_revision"], "status": state["status"], "benchmark_comparable": False},
        )
        art.add_file(str(state_path), name="state.json")
        logged = run.log_artifact(art, aliases=["latest", f"r{state['state_revision']}"])
        logged.wait()
        return {"artifact_ref": f"{self.entity}/{self.project}/{logged.name}", "version": logged.version, "digest": logged.digest, "state_revision": state["state_revision"]}

    # ---- waiting for ARIA --------------------------------------------------------------
    def wait_for(self, kind: str, revision: int, *, wait_seconds: int, poll_seconds: int, should_cancel: Callable[[], bool] | None = None, on_tick: Callable[[int], None] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """Block until ARIA publishes a proposal (kind='proposal') or final decision (kind='decision')."""
        if kind == "proposal":
            name, atype, filename = self.proposal_artifact_name(revision), PROPOSAL_TYPE, "proposal.json"
        elif kind == "decision":
            name, atype, filename = self.final_decision_artifact_name(), DECISION_TYPE, "decision.json"
        else:
            raise ValueError(kind)
        deadline = time.monotonic() + wait_seconds
        waited = 0
        while True:
            if should_cancel and should_cancel():
                raise ARIATimeout("cancelled while waiting for ARIA")
            artifact = self._fetch(name, atype)
            if artifact is not None:
                return self._download(artifact, filename)
            if time.monotonic() >= deadline:
                raise ARIATimeout(f"No {kind} artifact '{name}' arrived within {wait_seconds}s")
            if on_tick:
                on_tick(waited)
            time.sleep(poll_seconds)
            waited += poll_seconds

    def try_fetch(self, kind: str, revision: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Non-blocking single check (used by resume)."""
        try:
            return self.wait_for(kind, revision, wait_seconds=0, poll_seconds=1)
        except ARIATimeout:
            return None


# One automation with this run-name filter serves every session (session ids are wf-<date>-<time>-<hex>).
GENERIC_RUN_NAME_REGEX = r"^wf-.*-(exp-\d+|control-r\d+)$"


def automation_prompt(session_id: str | None, entity: str, project: str) -> str:
    """The prompt to paste into the W&B Automation ('Trigger ARIA' action). Must stay under 4000 chars.

    With session_id=None the prompt is generic: ARIA derives the session id from ${run_name}
    (run names are '<session>-exp-NNN' or '<session>-control-rN'), so one automation with
    GENERIC_RUN_NAME_REGEX as its run-name filter serves every session started from the UI or CLI.
    """
    if session_id:
        sess = session_id
        derive = ""
    else:
        sess = "<SESSION>"
        derive = (
            "SESSION = ${run_name} with its trailing '-exp-<digits>' or '-control-r<digits>' suffix removed "
            "(example: wf-20260913-101500-ab12-exp-002 -> wf-20260913-101500-ab12). Replace <SESSION> below with it.\n"
        )
    lines = [
        "You are the autonomous researcher for W&B project ${project_name}. Run ${run_name} just finished.",
        derive + "Goal: raise validation AUPRC for WildfireIA initial-attack failure (published test benchmark 0.533; validation scores are not test scores).",
        "Steps:",
        f"1. Using the wandb SDK, download artifact `{entity}/{project}/{sess}-state:latest` (type research-state) and read state.json. Trust only that state.",
        "2. Study objective, protocol, capabilities, history (scores, confusion, error_breakdowns, feature_importance), failed_experiments, rejected_messages_at_this_revision and instructions.",
        f"3. If instructions ask for a final decision: write decision.json following capabilities.response_contract.final_decision and log it as artifact `{sess}-decision-final` (type research-decision, alias latest). Stop.",
        "4. Otherwise decide KEEP/REJECT for awaiting_decision_for_experiment_id with reason, learning and next_question, then design ONE next experiment: an observation grounded in measured numbers, a falsifiable hypothesis, an expected result, and the reason. Change one meaningful variable when possible. Only use models, feature_protocols, weather_days and bounded hyperparameters listed in capabilities. Never repeat a configuration in history. Do not try to use test data.",
        f"5. Write proposal.json exactly following capabilities.response_contract.proposal with state_revision copied from the state and a unique proposal_id, then log it with wandb as artifact `{sess}-proposal-r<state_revision>` (type research-proposal, alias latest, metadata {{\"session_id\",\"state_revision\",\"conversation_note\"}}). Use wandb.init(project=\"{project}\", entity=\"{entity}\", job_type=\"aria-upload\", name=\"{sess}-aria-upload-r<state_revision>\") for the upload run.",
        "Respond only through those artifacts. Do not run training yourself.",
    ]
    return "\n".join(lines)

