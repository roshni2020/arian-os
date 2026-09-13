from pathlib import Path
import pytest
from scripts.setup_launch import copy_application_sources
from launch.job import verify_source_snapshot


def test_nested_sources_captured_and_drift_detected(tmp_path):
    root=tmp_path/'root';stage=tmp_path/'stage';stage.mkdir()
    for name in ['wildfire_researcher/api.py','wildfire_researcher/benchmarks/routes.py','scripts/run_launch_step.py']:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# trusted source\n')
    (root/'wildfire_researcher'/'credentials.env').write_text('do not capture')
    (root/'wildfire_researcher'/'cache.json').write_text('{}')
    copy_application_sources(root,stage)
    assert (stage/'wildfire_researcher'/'benchmarks'/'routes.py').is_file()
    assert not list(stage.rglob('*.env')) and not list(stage.rglob('*.json'))
    verify_source_snapshot(stage,root)
    nested=root/'wildfire_researcher'/'benchmarks'/'routes.py'
    nested.write_text('# changed\n')
    with pytest.raises(ValueError,match='changed'):
        verify_source_snapshot(stage,root)
    copy_application_sources(root,stage)
    (root/'wildfire_researcher'/'benchmarks'/'new.py').write_text('# newly added\n')
    with pytest.raises(ValueError,match='changed'):
        verify_source_snapshot(stage,root)
