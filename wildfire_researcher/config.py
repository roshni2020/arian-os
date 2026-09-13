"""Environment and path configuration. Secrets are never stored here."""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional .env support for local development
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except Exception:  # pragma: no cover - dotenv is optional
    pass

ROOT = Path(os.environ.get("WILDFIRE_RESEARCHER_ROOT", Path(__file__).resolve().parents[1]))
WILDFIREIA_DIR = Path(os.environ.get("WILDFIREIA_DIR", ROOT / "WildfireIA"))
CANONICAL_DIR = WILDFIREIA_DIR / "data" / "canonical" / "raw_feature_tables"
CACHE_DIR = WILDFIREIA_DIR / "data" / "cache" / "model_ready"
DATA_DIR = ROOT / "data"
ARTIFACTS_DIR = ROOT / "artifacts"
DB_PATH = Path(os.environ.get("RESEARCHER_DB_PATH", DATA_DIR / "researcher.sqlite"))

WANDB_ENTITY = os.environ.get("WANDB_ENTITY", "ali-amjad52114-r42")
WANDB_PROJECT = os.environ.get("WANDB_PROJECT", "wildfire-autonomous-researcher")

# connected: real ARIA through W&B Automations + Artifacts (the only judged mode)
# fallback:  development-only deterministic stub, always labelled, never silent
# replay:    read stored verified records, no training, no ARIA calls
ARIA_MODE = os.environ.get("ARIA_MODE", "connected").strip().lower()
FAST_MODE = os.environ.get("FAST_MODE", "false").strip().lower() in {"1", "true", "yes"}
DEFAULT_BUDGET = int(os.environ.get("EXPERIMENT_BUDGET", "15"))
ARIA_WAIT_SECONDS = int(os.environ.get("ARIA_WAIT_SECONDS", "1800"))
ARIA_POLL_SECONDS = int(os.environ.get("ARIA_POLL_SECONDS", "15"))
ARIA_MAX_REJECTIONS = int(os.environ.get("ARIA_MAX_REJECTIONS", "3"))
# If ARIA has not answered within this many seconds, re-publish the state through a control run
# (W&B occasionally drops a run-finished event); give up after ARIA_MAX_NUDGES nudges per revision cycle.
ARIA_NUDGE_SECONDS = int(os.environ.get("ARIA_NUDGE_SECONDS", "180"))
ARIA_MAX_NUDGES = int(os.environ.get("ARIA_MAX_NUDGES", "2"))
MAX_RUNTIME_SECONDS = int(os.environ.get("MAX_RUNTIME_SECONDS", "1800"))

TARGET_AUPRC = 0.533


def credential_present() -> bool:
    return bool(os.environ.get("WANDB_API_KEY"))


def load_wandb_credential() -> None:
    """Populate WANDB_API_KEY from the per-user Windows environment if the process did not inherit it."""
    if os.environ.get("WANDB_API_KEY"):
        return
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                os.environ["WANDB_API_KEY"] = winreg.QueryValueEx(key, "WANDB_API_KEY")[0]
        except OSError:
            pass
    if not os.environ.get("WANDB_API_KEY"):
        raise RuntimeError("WANDB_API_KEY is required for W&B, Weave and the ARIA exchange")
