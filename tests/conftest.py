"""Keep test execution leases isolated from the user's live research worker."""
import pytest
from wildfire_researcher import config


@pytest.fixture(autouse=True)
def isolated_worker_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path/'runtime')
