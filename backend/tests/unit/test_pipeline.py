"""Pipeline: created / grouped / filtered / duplicate, proposals, and device status."""
import json

import pytest

from alerts import pipeline
from alerts.normalise import normalise


def raw(rule="60204", level=10, name="RECEPTION-PC", ip="192.168.1.57", external_id=None, source="replay", failures=None):
    shield = {"failures": failures, "window_minutes": 4} if failures else None
    return {"source": source, "external_id": external_id, "shieldmate": shield, "alert": {
        "rule": {"id": rule, "level": level}, "agent": {"name": name},
        "data": {"win": {"eventdata": ({"targetUserName": "u", "ipAddress": ip} if ip else {"targetUserName": "u"})}}}}


@pytest.fixture
def h(make_app):
    h = make_app(actions=True)
    h.reset()
    return h


def run(h, r):
    return pipeline.process(normalise(r, "2026-11-01T04:00:00Z"), h.ctx.db, h.clock, lessons=h.ctx.lessons, config=h.config)


def test_first_card_uses_rule_default_count(h):
    assert run(h, raw()) == "created"
    assert h.ctx.db.one("SELECT count FROM alerts")["count"] == 8           # decision 18


def test_grouped_without_explicit_count_bumps_by_one(h):
    run(h, raw()); assert run(h, raw()) == "grouped"
    assert h.ctx.db.one("SELECT count FROM alerts")["count"] == 9


def test_different_agent_is_a_new_card(h):
    run(h, raw()); assert run(h, raw(name="DOCTOR-PC")) == "created"


def test_low_level_and_unknown_rule_are_filtered_and_counted(h):
    assert run(h, raw("60106", 3)) == "filtered" and run(h, raw("550", 7)) == "filtered"
    assert h.get("/alerts?role=owner").json() == {"hidden_count": 2, "alerts": []}


def test_duplicate_external_id_is_ignored(h):
    assert run(h, raw(external_id="abc", source="wazuh")) == "created"
    assert run(h, raw(external_id="abc", source="wazuh")) == "duplicate"
    assert h.ctx.db.one("SELECT count(*) AS n FROM alerts")["n"] == 1


def test_t4_01_password_alert_proposes_block_for_its_source_ip(h):
    run(h, raw())
    a = h.get("/actions").json()["actions"][0]
    assert (a["target_ip"], a["status"], a["simulated"], a["label"]) == ("192.168.1.57", "proposed", True, "Block 192.168.1.57 for 60 minutes")


def test_t4_01_ransomware_proposes_nothing(h):
    h.inject("ransomware")
    assert h.get("/actions").json() == {"actions": []}


@pytest.mark.parametrize("ip,reason", [("192.168.1.1", "192.168.1.1 is the clinic router"), (None, None)])
def test_refused_targets_are_stored_with_a_reason(h, ip, reason):
    run(h, raw(ip=ip))
    a = h.get("/actions").json()["actions"][0]
    assert a["status"] == "refused" and a["target_ip"] == ip
    if reason:
        assert a["refused_reason"] == reason


def test_t4_13_no_proposals_when_actions_off(app_h):
    app_h.reset(); app_h.inject("password_guessing")
    assert app_h.ctx.db.one("SELECT count(*) AS n FROM actions")["n"] == 0
    assert app_h.get("/alerts?role=owner").json()["alerts"][0]["action"] is None


def test_live_source_alert_is_not_simulated(h):
    run(h, raw(source="wazuh", external_id="x1"))
    assert h.get("/actions").json()["actions"][0]["simulated"] is False


def test_new_60204_marks_device_under_attack(h, monkeypatch):
    import routes.devices as devices
    seen = []
    monkeypatch.setattr(devices, "set_device_status", lambda db, n, s, w: seen.append((n, s)), raising=False)
    run(h, raw())
    assert seen == [("RECEPTION-PC", "under_attack")]


def test_missing_lane_two_helper_is_a_no_op(h):
    run(h, raw())        # routes.devices has no set_device_status yet: must not raise
