"""T0.05: replay file loads, 5 records, clicks as designed; cursor, exhaustion and reset."""
import json

import pytest

from clock import FakeClock
from config import Config
from ingest.replay import ReplayExhausted, ReplayFileError, ReplaySource

CONFIG = Config()


def source():
    return ReplaySource(CONFIG.replay_path, FakeClock())


def test_file_has_five_records_in_the_designed_clicks():
    s = source()
    assert len(json.loads(CONFIG.replay_path.read_text())) == 5
    click1, first = s.next_click("password_guessing")
    assert (click1, len(first)) == (1, 2)
    click2, second = s.next_click("password_guessing")
    assert (click2, len(second)) == (2, 1)
    assert [r["alert"]["rule"]["id"] for r in s.next_click("ransomware")[1]] == ["550", "100201"]


def test_records_are_stamped_with_now_and_carry_shieldmate_counts():
    _, batch = source().next_click("password_guessing")
    assert all(r["alert"]["timestamp"] == "2026-11-01T04:00:00Z" for r in batch)
    assert batch[1]["shieldmate"] == {"failures": 8, "window_minutes": 4}
    assert batch[0]["shieldmate"] is None and batch[0]["source"] == "replay"


def test_exhaustion_then_reset():
    s = source()
    s.next_click("ransomware")
    assert s.clicks_left("ransomware") == 0
    with pytest.raises(ReplayExhausted):
        s.next_click("ransomware")
    s.reset_state()
    assert s.clicks_left("ransomware") == 1
    assert s.next_click("ransomware")[0] == 1


def test_gap_in_clicks_is_rejected(tmp_path):
    bad = tmp_path / "r.json"
    bad.write_text(json.dumps([{"replay": {"type": "ransomware", "click": 2}, "alert": {
        "rule": {"id": "1", "level": 1}, "agent": {"name": "A"}}}]))
    with pytest.raises(ReplayFileError):
        ReplaySource(bad, FakeClock())
