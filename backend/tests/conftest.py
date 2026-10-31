"""Shared test setup: a temp DB, FakeClock, FakeWazuhClient and a TestClient per test.

``backend/`` is put on sys.path (the packages are namespace packages with no __init__.py),
so tests import ``alerts.filter``, ``main`` etc. the same way the app does.

    def test_x(make_app):
        h = make_app(actions=True)        # Config overrides; flags default to off
        h.reset(); h.inject("password_guessing")
        h.advance(301); h.tick()
"""
from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from actions import timeout  # noqa: E402
from actions.wazuh_client import FakeWazuhClient  # noqa: E402
from clock import FakeClock  # noqa: E402
from config import Config  # noqa: E402
from main import create_app  # noqa: E402


@dataclass
class Harness:
    client: TestClient
    clock: FakeClock
    wazuh: FakeWazuhClient
    config: Config
    ctx: object

    def reset(self):
        r = self.client.post("/api/demo/reset")
        assert r.status_code == 200, r.text
        return r.json()

    def inject(self, alert_type: str):
        r = self.client.post(f"/api/demo/replay/{alert_type}")
        assert r.status_code == 200, r.text
        return r.json()

    def advance(self, seconds: float) -> None:
        self.clock.advance(seconds)

    def tick(self) -> dict:
        """Run one 10 s background pass now."""
        return timeout.run_once(self.ctx.db, self.clock, self.config, self.wazuh)

    def get(self, path, **kw):
        return self.client.get("/api" + path, **kw)

    def post(self, path, **kw):
        return self.client.post("/api" + path, **kw)

    def put(self, path, **kw):
        return self.client.put("/api" + path, **kw)

    def events(self, prefix: str = "") -> list[dict]:
        """This app's event log, oldest first, with ``data`` decoded; ``prefix`` filters by type."""
        conn = sqlite3.connect(self.config.events_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM events WHERE type LIKE ? ORDER BY id", (prefix + "%",)).fetchall()
        finally:
            conn.close()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]


@pytest.fixture
def make_app(tmp_path):
    """Factory: ``make_app(actions=True, ...)`` builds an isolated app. Flags default to off."""
    opened: list[TestClient] = []

    def factory(wazuh: FakeWazuhClient | None = None, **overrides) -> Harness:
        config = Config(
            db_path=tmp_path / f"t{len(opened)}.db",
            restore_sandbox_dir=tmp_path / "sandbox",
            **overrides,
        )
        clock = FakeClock()
        wazuh = wazuh or FakeWazuhClient()
        app = create_app(config, clock, wazuh_client=wazuh, background=False)
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()                    # runs the lifespan
        opened.append(client)
        return Harness(client, clock, wazuh, config, app.state.ctx)

    yield factory
    for c in opened:
        c.__exit__(None, None, None)


@pytest.fixture
def app_h(make_app) -> Harness:
    """Default app: flags off, replay mode."""
    return make_app()


@pytest.fixture
def actions_h(make_app) -> Harness:
    """App with ACTIONS on (proposals, approval cards, /devices)."""
    return make_app(actions=True)
