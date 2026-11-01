"""Live Wazuh ingest (WazuhSource): mocked client only, never the network.

A fake client stands in for RealWazuhClient.alert_hits, so these cover the cursor, the
look-back, dedupe and how a live hit looks once it goes through the normal pipeline.
"""
import copy
import json
import logging

import pytest

from actions.wazuh_client import FakeWazuhClient, WazuhApiError
from alerts import pipeline
from alerts.normalise import normalise
from clock import FakeClock
from config import Config
from ingest.replay import ReplaySource
from ingest.wazuh import LOOKBACK, WazuhSource
from main import build_context


def hit(doc_id="AbC1", *, rule="60204", level=10, agent="RECEPTION-PC", ip="192.168.1.57",
        user="admin", index="wazuh-alerts-4.x-2026.11.01"):
    """A hit shaped like an indexer search result (no ``shieldmate`` block, as live alerts have)."""
    return {"_index": index, "_id": doc_id, "_source": {
        "timestamp": "2026-11-01T04:00:10Z",
        "rule": {"id": rule, "level": level, "description": "Multiple Windows Logon Failures"},
        "agent": {"id": "003", "name": agent},
        "data": {"win": {"eventdata": {"targetUserName": user, "ipAddress": ip}}}}}


class FakeIndexer(FakeWazuhClient):
    """FakeWazuhClient plus alert_hits: records each (start, end) and can be told to fail."""

    def __init__(self, hits=(), fail=False):
        super().__init__()
        self.hits, self.fail, self.windows = list(hits), fail, []

    def alert_hits(self, start, end):
        self.windows.append((start, end))
        if self.fail:
            raise WazuhApiError("indexer down")
        yield from self.hits


def source(hits=(), **kw):
    clock = FakeClock()
    client = FakeIndexer(hits, **kw)
    return WazuhSource(None, clock, client=client), client, clock


# --- RawAlert shape -----------------------------------------------------------------------

def test_hit_becomes_raw_alert_with_unchanged_alert():
    h = hit()
    src, _, _ = source([h])
    original = copy.deepcopy(h["_source"])
    (raw,) = src.next_batch()
    assert raw == {"source": "wazuh", "external_id": "wazuh-alerts-4.x-2026.11.01:AbC1",
                   "alert": original, "shieldmate": None}
    assert raw["alert"] is h["_source"]          # passed through, not rebuilt


def test_same_id_in_another_index_is_a_different_alert():
    src, _, _ = source([hit("X", index="a"), hit("X", index="b")])
    assert [r["external_id"] for r in src.next_batch()] == ["a:X", "b:X"]


def test_malformed_hit_is_skipped_not_fatal(caplog):
    src, _, _ = source([{"_source": {}}, hit("ok")])
    with caplog.at_level(logging.WARNING, logger="shieldmate"):
        batch = src.next_batch()
    assert [r["external_id"].endswith(":ok") for r in batch] == [True]
    assert "skipped a Wazuh hit" in caplog.text


# --- cursor and look-back -----------------------------------------------------------------

def test_first_poll_never_reaches_before_startup():
    src, client, clock = source()
    started = clock.now()
    clock.advance(5)
    src.next_batch()
    assert client.windows == [(started, clock.now())]       # look-back is clamped to start-up


def test_look_back_is_two_minutes_after_a_success():
    src, client, clock = source()
    clock.advance(300)
    src.next_batch()
    clock.advance(5)
    src.next_batch()
    (_, first_end), (second_start, _) = client.windows
    assert second_start == first_end - LOOKBACK


def test_cursor_does_not_advance_after_a_failure():
    src, client, clock = source()
    clock.advance(300)
    src.next_batch()                                         # ok: cursor = t+300
    clock.advance(5)
    client.fail = True
    with pytest.raises(WazuhApiError):
        src.next_batch()
    failed_start = client.windows[-1][0]
    clock.advance(5)
    client.fail = False
    src.next_batch()                                         # retry asks from the same start
    assert client.windows[-1][0] == failed_start


def test_ids_from_a_failed_poll_are_not_marked_seen():
    class Flaky(FakeIndexer):
        def alert_hits(self, start, end):
            self.windows.append((start, end))
            yield self.hits[0]
            if self.fail:
                raise WazuhApiError("died mid-scroll")      # after one page was already yielded
            yield from self.hits[1:]

    clock = FakeClock()
    client = Flaky([hit("1"), hit("2")], fail=True)
    src = WazuhSource(None, clock, client=client)
    with pytest.raises(WazuhApiError):
        src.next_batch()
    client.fail = False
    assert [r["external_id"][-1] for r in src.next_batch()] == ["1", "2"]    # nothing was lost


def test_look_back_refetch_is_not_returned_twice():
    src, _, clock = source([hit("A")])
    assert len(src.next_batch()) == 1
    clock.advance(5)
    assert src.next_batch() == []                            # same hit comes back from the look-back


def test_seen_ids_are_pruned_once_older_than_the_look_back():
    src, client, clock = source([hit("A")])
    src.next_batch()
    client.hits = []
    clock.advance(LOOKBACK.total_seconds() + 10)
    src.next_batch()
    assert src._seen == {}


# --- through the real pipeline ------------------------------------------------------------

def ingest(h, raw_batch):
    """What main._ingest_loop does for each RawAlert."""
    for raw in raw_batch:
        pipeline.process(normalise(raw, "2026-11-01T04:00:00Z"), h.ctx.db, h.clock,
                         lessons=h.ctx.lessons, config=h.config)


def test_live_60204_makes_a_front_desk_card_with_log_fields(app_h):
    src = WazuhSource(None, app_h.clock, client=FakeIndexer([hit()]))
    app_h.advance(5)
    ingest(app_h, src.next_batch())

    (alert,) = app_h.get("/alerts?role=front_desk").json()["alerts"]
    assert alert["source"] == "wazuh" and alert["rule_id"] == "60204"
    assert alert["count"] == 8                                # count_defaults, decision 18
    assert "8" in alert["card"]["what_we_know"] and "4 minutes" in alert["card"]["what_we_know"]
    # Both fields are stored verbatim; lessons.json decides who sees what (front desk: username only).
    stored = json.loads(app_h.ctx.db.one("SELECT log_fields FROM alerts")["log_fields"])
    assert stored == {"username_tried": "admin", "source_ip": "192.168.1.57"}
    assert alert["card"]["log_fields"] == {"username_tried": "admin"}
    (owner,) = app_h.get("/alerts?role=owner").json()["alerts"]
    assert owner["card"]["log_fields"] == stored


def test_duplicate_hit_makes_only_one_card(app_h):
    h = hit()
    ingest(app_h, [{"source": "wazuh", "external_id": "i:1", "alert": h["_source"], "shieldmate": None}] * 2)
    assert app_h.ctx.db.one("SELECT count(*) AS n FROM alerts")["n"] == 1


def test_a_refetched_grouped_hit_does_not_bump_the_count_again(app_h):
    src = WazuhSource(None, app_h.clock, client=FakeIndexer([hit("A"), hit("B")]))
    app_h.advance(5)
    ingest(app_h, src.next_batch())                          # A -> new card (8), B -> grouped (9)
    app_h.advance(5)
    ingest(app_h, src.next_batch())                          # both come back from the look-back
    rows = app_h.ctx.db.query("SELECT count FROM alerts")
    assert [r["count"] for r in rows] == [9]


def test_live_alert_never_calls_the_wazuh_client_for_a_block(actions_h):
    # ACTIONS on: a live 60204 creates a *proposal*, never a block, until someone approves.
    src = WazuhSource(None, actions_h.clock, client=FakeIndexer([hit()]))
    actions_h.advance(5)
    ingest(actions_h, src.next_batch())
    assert actions_h.wazuh.calls == []
    assert actions_h.ctx.db.one("SELECT status, simulated FROM actions")["simulated"] == 0


def ransom_hit(doc_id="R1", **rule_extra):
    return {"_index": "wazuh-alerts-4.x-2026.11.01", "_id": doc_id, "_source": {
        "timestamp": "2026-11-01T04:00:10Z",
        "rule": {"id": "100201", "level": 12, "description": "Possible ransomware", **rule_extra},
        "agent": {"id": "003", "name": "RECEPTION-PC"},
        "syscheck": {"path": "D:\Shared\a.xlsx.locked", "event": "added"}}}


def test_100201_block_prefers_frequency_then_firedtimes_then_omits():
    src, _, clock = source([ransom_hit("a", frequency=52, firedtimes=3), ransom_hit("b", firedtimes=3),
                            ransom_hit("c"), hit("d")])
    clock.advance(5)
    blocks = [r["shieldmate"] for r in src.next_batch()]
    assert blocks == [{"files_renamed": 52, "window_minutes": 1}, {"files_renamed": 3, "window_minutes": 1},
                      {"window_minutes": 1}, None]


def test_live_100201_makes_a_ransomware_card_and_proposes_no_action(actions_h):
    src = WazuhSource(None, actions_h.clock, client=FakeIndexer([ransom_hit(frequency=52)]))
    actions_h.advance(5)
    (raw,) = src.next_batch()
    assert raw["shieldmate"]["files_renamed"] == 52
    ingest(actions_h, [raw])                                  # ACTIONS on, so a block *could* be proposed

    (alert,) = actions_h.get("/alerts?role=owner").json()["alerts"]
    assert alert["rule_id"] == "100201" and alert["source"] == "wazuh"
    assert "52 files" in alert["card"]["what_we_know"]        # files_renamed, not the lesson default 37
    assert actions_h.ctx.db.one("SELECT count(*) AS n FROM actions")["n"] == 0
    assert actions_h.wazuh.calls == []


# --- compatibility and start-up -----------------------------------------------------------

def test_old_imports_from_wazuh_client_still_work():
    from actions.wazuh_client import WazuhPoller, normalise as old_normalise
    from ingest import wazuh
    assert WazuhPoller is wazuh.WazuhPoller and old_normalise is wazuh.normalise
    with pytest.raises(ImportError):
        from actions.wazuh_client import no_such_name  # noqa: F401


def test_broken_lab_config_leaves_wazuh_source_out_and_app_on_replay(tmp_path, caplog):
    cfg = Config(alert_source="wazuh", db_path=tmp_path / "db.sqlite",
                 restore_sandbox_dir=tmp_path / "sandbox")
    with caplog.at_level(logging.WARNING, logger="shieldmate"):
        ctx = build_context(cfg, FakeClock())
    assert isinstance(ctx.source, ReplaySource)
    assert "Wazuh source could not start" in caplog.text
