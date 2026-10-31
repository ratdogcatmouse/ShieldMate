"""Live-mode startup fallback (T5.09): a broken lab config must not take down the app.

The spec says the lab can be switched off mid-demo and Backstage replay must keep
working *without a restart*. So main.build_context degrades to the replay source and
the fake client instead of letting a misconfigured RealWazuhClient raise at start-up.
"""
import contextlib
import logging

from actions.wazuh_client import FakeWazuhClient
from clock import RealClock
from config import Config
from ingest.replay import ReplaySource
from main import build_context, create_app


@contextlib.contextmanager
def quiet():
    """The fallback logs warnings; keep the test output clean."""
    logger = logging.getLogger("shieldmate")
    old = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        logger.setLevel(old)


def test_misconfigured_wazuh_client_falls_back_to_fake(tmp_path):
    # Complete-looking but unusable (CA cert missing on disk): the old code raised
    # FileNotFoundError here and the whole server would fail to start.
    cfg = Config(alert_source="wazuh",
                 wazuh_api_url="https://manager:55000", wazuh_indexer_url="https://indexer:9200",
                 wazuh_ca_cert=str(tmp_path / "no-such-ca.pem"),
                 db_path=tmp_path / "db.sqlite",
                 restore_sandbox_dir=tmp_path / "sandbox")
    with quiet():
        ctx = build_context(cfg, RealClock())
    assert isinstance(ctx.source, ReplaySource)      # live ingest falls back to replay
    assert isinstance(ctx.wazuh, FakeWazuhClient)    # and so does the client


def test_empty_wazuh_settings_fall_back_too(tmp_path):
    cfg = Config(alert_source="wazuh", db_path=tmp_path / "db.sqlite",
                 restore_sandbox_dir=tmp_path / "sandbox")
    with quiet():
        ctx = build_context(cfg, RealClock())
    assert isinstance(ctx.wazuh, FakeWazuhClient)


def test_misconfigured_live_mode_app_still_serves_the_api(tmp_path):
    cfg = Config(alert_source="wazuh", db_path=tmp_path / "db.sqlite",
                 restore_sandbox_dir=tmp_path / "sandbox")
    with quiet():
        app = create_app(cfg, clock=RealClock(), background=False)
        assert isinstance(app.state.ctx.wazuh, FakeWazuhClient)
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as test:
        r = test.post("/api/demo/reset")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert test.get("/api/clinic").status_code == 200
