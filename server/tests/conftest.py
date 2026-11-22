import os
import sys
from concurrent.futures import Future

import pytest

os.environ["RW_NO_AUTOAPP"] = "1"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["DEMO_DELAY_MIN"] = "0"
os.environ["DEMO_DELAY_MAX"] = "0"
os.environ["YDC_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server import checks, config, db, jobs  # noqa: E402


class SyncPool:
    """Runs submitted work immediately so tests are deterministic."""

    def submit(self, fn, *a, **k):
        f = Future()
        try:
            f.set_result(fn(*a, **k))
        except Exception as e:  # noqa: BLE001
            f.set_exception(e)
        return f


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(jobs, "OUTER", SyncPool())
    monkeypatch.setattr(checks, "INNER", SyncPool())
    config.set_demo(None)
    monkeypatch.setenv("DEMO_MODE", "on")
    db.init()
    yield
    config.set_demo(None)


@pytest.fixture()
def client(env):
    from server.app import create_app

    return create_app().test_client()
