"""Verify package capture/drift without W&B writes, Launch dispatch or training."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launch_capture_includes_nested_package_and_excludes_non_source(tmp_path, monkeypatch):
    module = load_module("acceptance_setup_launch", "scripts/setup_launch.py")
    root = tmp_path / "workspace"
    for relative, contents in {
        "launch/job.py": "# trusted bridge\n", "launch/requirements.txt": "wandb\n",
        "wildfire_researcher/api.py": "# api\n",
        "wildfire_researcher/benchmarks/routes.py": "# nested trusted source\n",
        "wildfire_researcher/benchmarks/.env": "DO_NOT_PACKAGE=secret-placeholder\n",
        "wildfire_researcher/benchmarks/cache.json": "{}",
        "wildfire_researcher/benchmarks/__pycache__/routes.pyc": "compiled-cache",
        "scripts/run_launch_step.py": "# bridge helper\n",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    artifacts = tmp_path / "artifacts"
    setup = artifacts / "operations/launch/setup.json"
    setup.parent.mkdir(parents=True)
    setup.write_text(json.dumps({"session_id": "existing-id", "budget": 1, "source_fingerprint": "old"}))
    monkeypatch.setattr(module.config, "ROOT", root)
    monkeypatch.setattr(module.config, "ARTIFACTS_DIR", artifacts)
    monkeypatch.setattr(module.config, "load_wandb_credential", lambda: None)
    monkeypatch.setattr(module.wandb, "Api", lambda: SimpleNamespace(run_queue=lambda *args: SimpleNamespace(type="local-process")))
    created = []
    def capture(**kwargs):
        stage = Path(kwargs["path"])
        paths = {p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()}
        assert "wildfire_researcher/benchmarks/routes.py" in paths
        assert not any(p.endswith((".env", ".json", ".pyc")) for p in paths)
        created.append(stage)
        return SimpleNamespace(qualified_name="test/job:v1", digest="test-digest")
    monkeypatch.setattr(module, "create_job", capture)
    monkeypatch.setattr(module, "create_launch_session", Mock(side_effect=AssertionError("No session creation")))
    monkeypatch.setattr(module.sys, "argv", ["setup_launch.py"])
    module.main()
    saved = json.loads(setup.read_text())
    assert saved["session_id"] == "existing-id"
    assert "wildfire_researcher/benchmarks/routes.py" in {p.replace("\\", "/") for p in saved["source_sha256"]}
    fingerprint = saved["source_fingerprint"]
    (root / "wildfire_researcher/benchmarks/routes.py").write_text("# updated nested source\n")
    module.main()
    assert len(created) == 2
    assert json.loads(setup.read_text())["source_fingerprint"] != fingerprint


def test_launch_drift_checks_nested_source_before_any_execution(tmp_path, monkeypatch):
    module = load_module("acceptance_launch_bridge", "launch/job.py")
    snapshot = tmp_path / "snapshot"
    local = tmp_path / "local"
    for base in (snapshot, local):
        for relative in ("wildfire_researcher/api.py", "wildfire_researcher/benchmarks/routes.py", "scripts/run_launch_step.py"):
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# original\n")
    (local / "wildfire_researcher/benchmarks/routes.py").write_text("# drifted\n")
    monkeypatch.setattr(module, "__file__", str(snapshot / "job.py"))
    monkeypatch.setattr(module, "Path", lambda value: local if str(value) == "/mnt/c/AI/Projects/focus" else Path(value))
    class Run:
        config = {}
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr(module.wandb, "init", lambda **kwargs: Run())
    dispatch = Mock(side_effect=AssertionError("No subprocess/Launch execution permitted"))
    monkeypatch.setattr(module.subprocess, "run", dispatch)
    with pytest.raises(ValueError, match="changed"):
        module.main()
    dispatch.assert_not_called()


@pytest.mark.parametrize("change", ["added", "removed"])
def test_launch_drift_rejects_package_pathset_changes(tmp_path, change):
    module = load_module("acceptance_launch_pathset", "launch/job.py")
    snapshot, local = tmp_path / "snapshot", tmp_path / "local"
    for base in (snapshot, local):
        for relative in ("wildfire_researcher/api.py", "wildfire_researcher/benchmarks/routes.py", "scripts/run_launch_step.py"):
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# source\n")
    module.verify_source_snapshot(snapshot, local)
    if change == "added":
        (local / "wildfire_researcher/benchmarks/new.py").write_text("# new source\n")
    else:
        (local / "wildfire_researcher/benchmarks/routes.py").unlink()
    with pytest.raises(ValueError, match="changed"):
        module.verify_source_snapshot(snapshot, local)
