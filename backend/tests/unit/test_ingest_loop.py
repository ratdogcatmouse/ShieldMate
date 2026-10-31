"""The live-ingest loop: one malformed alert is skipped, the rest of the batch is still stored."""
import asyncio

from alerts.normalise import normalise
from clock import FakeClock
from main import _ingest_loop


class Ctx:
    """Just the parts of Context the loop touches."""
    def __init__(self, base, batch):
        self.db, self.clock, self.lessons, self.config = base.db, base.clock, base.lessons, base.config
        self.wazuh = base.wazuh
        self.wazuh_health = {}
        self.source = type("S", (), {"next_batch": lambda _self: batch})()


def test_malformed_alert_does_not_drop_the_batch(app_h):
    app_h.reset()
    good = app_h.ctx.replay.next_click("password_guessing")[1][1]       # the 60204 record
    batch = [{"source": "wazuh", "external_id": "bad", "alert": {"rule": {}}, "shieldmate": None}, good]

    async def run_briefly():
        task = asyncio.create_task(_ingest_loop(Ctx(app_h.ctx, batch), 0.01))
        await asyncio.sleep(0.05)
        task.cancel()
    asyncio.run(run_briefly())

    assert app_h.get("/alerts?role=owner").json()["alerts"]            # the good alert got through
