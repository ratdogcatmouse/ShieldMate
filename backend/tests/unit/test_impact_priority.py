"""Impact priority (T7): seed validation, the four worked examples, and the alert/strip surfaces."""
from __future__ import annotations

import json

import pytest

from alerts import impact
from config import Config

_SEED_IMPACT = {
    "services": {"patient records": 5, "billing": 4, "appointments": 4,
                 "consultations": 3, "front-desk check-in": 2},
    "accounts": {"owner": 5, "billing": 3, "front_desk": 2},
    "damage": {"encrypted": 3, "infected": 2, "compromised": 2, "isolated": 1, "ok": 0},
    "bands": [4, 8, 16],
    "device_accounts": {"RECEPTION-PC": "front_desk", "FILE-SERVER": "billing", "DOCTOR-PC": "owner"},
    "rules": {"60204": {"damage": "isolated", "account": "device"},
              "60106": {"damage": "infected", "account": "device"},
              "61320": {"damage": "infected", "account": "device"},
              "100201": {"damage": "encrypted", "account": "none"}},
}


def _write(tmp_path, block):
    p = tmp_path / "seed.json"
    p.write_text(json.dumps({"impact": block}))
    return p


def _book(tmp_path, **overrides):
    p = _write(tmp_path, {**_SEED_IMPACT, **overrides})
    return impact.ImpactBook.load(p)


def _dev(agent, status="ok", services=None):
    return {"agent_name": agent, "status": status, "services": services or []}


def _no_damage_block(tmp_path, **overrides):
    block = {"services": {}, "accounts": {}, "damage": {}, "bands": [4, 8, 16], **overrides}
    return _write(tmp_path, block)


# --- T7.01: the seed's impact block is validated on load ---------------------------

def test_seed_block_is_valid(tmp_path):
    assert _book(tmp_path).data["bands"] == [4, 8, 16]


def test_validation_rejects_a_negative_weight(tmp_path):
    p = _write(tmp_path, {**_SEED_IMPACT, "services": {"patient records": -1}})
    with pytest.raises(impact.ImpactError):
        impact.ImpactBook.load(p)


def test_validation_rejects_missing_damage_state(tmp_path):
    damage = dict(_SEED_IMPACT["damage"])
    del damage["compromised"]
    p = _write(tmp_path, {**_SEED_IMPACT, "damage": damage})
    with pytest.raises(impact.ImpactError):
        impact.ImpactBook.load(p)


def test_validation_rejects_non_ascending_bands(tmp_path):
    p = _write(tmp_path, {**_SEED_IMPACT, "bands": [8, 4, 16]})
    with pytest.raises(impact.ImpactError):
        impact.ImpactBook.load(p)


def test_missing_block_degrades_to_empty(tmp_path):
    p = tmp_path / "s.json"; p.write_text(json.dumps({"impact": None}))
    assert impact.ImpactBook.load(p).data in (None, {})


# --- T7.02: the four worked examples ------------------------------------------------

def test_four_worked_examples(tmp_path):
    book = _book(tmp_path)
    cases = [
        (_dev("RECEPTION-PC", services=["Front-desk check-in"]), "60204", "low", 4),
        (_dev("FILE-SERVER", services=["Appointments", "Billing", "Patient records"]), "60204", "high", 16),
        (_dev("FILE-SERVER", services=["Appointments", "Billing", "Patient records"]), "100201", "critical", 39),
        (_dev("DOCTOR-PC", services=["Consultations"]), "61320", "high", 11),
    ]
    for device, rule, level, score in cases:
        out = impact.alert_out(book, device, rule, "new")
        assert out["level"] == level and out["score"] == score, (rule, level, out)


def test_filtered_or_unknown_device_gets_no_impact(tmp_path):
    book = _book(tmp_path)
    # filtered noise never gets an impact object (the filter keeps doing its job).
    assert impact.alert_out(book, _dev("DOCTOR-PC", services=["Consultations"]), "61320", "filtered") is None
    # a device with nothing at risk (no weighted services, no account) scores 0 -> None.
    assert impact.alert_out(book, _dev("GHOST-PC", services=["Nonexistent service"]), "61320", "new") is None


def test_notification_prefix_high_and_critical_only(tmp_path):
    book = _book(tmp_path)
    crit = impact.alert_out(book, _dev("FILE-SERVER", status="new",
                                       services=["Appointments", "Billing", "Patient records"]), "100201", "new")
    low = impact.alert_out(book, _dev("RECEPTION-PC", status="new", services=["Front-desk check-in"]), "60204", "new")
    assert impact.notification_prefix(crit) == "[CRITICAL] "
    assert impact.notification_prefix(low) == ""


# --- T7.04: the device strip exposes impact only when under_attack -----------------

def test_strip_shows_impact_only_when_under_attack(tmp_path):
    book = _book(tmp_path)
    srv = ["Appointments", "Billing", "Patient records"]
    out = impact.device_strip(book, _dev("FILE-SERVER", status="under_attack", services=srv))
    assert out is not None and out["level"] in ("medium", "high", "critical")
    assert impact.device_strip(book, _dev("FILE-SERVER", status="ok", services=srv)) is None
    assert impact.device_strip(book, _dev("FILE-SERVER", status="protected", services=srv)) is None


# --- T7.05: the owner queue can sort by impact --------------------------------------

def test_owner_queue_sorts_by_impact(app_h):
    app_h.reset()
    app_h.inject("ransomware")              # critical: FILE-SERVER
    app_h.inject("password_guessing")       # low: RECEPTION-PC
    body = app_h.get("/alerts?role=owner&sort=impact").json()
    scores = [a["impact"]["score"] for a in body["alerts"] if a["impact"] is not None]
    assert scores == sorted(scores, reverse=True)        # highest impact on top


def test_time_sort_is_the_default(app_h):
    app_h.reset()
    app_h.inject("password_guessing")
    app_h.inject("ransomware")
    body = app_h.get("/alerts?role=owner").json()
    assert [a["rule_id"] for a in body["alerts"]] == ["100201", "60204"]  # newest last_seen first


# --- T7.07: the alert and device surfaces carry an impact object --------------------

def test_alert_out_carries_impact(app_h):
    app_h.reset()
    app_h.inject("password_guessing")
    alert = app_h.get("/alerts?role=front_desk").json()["alerts"][0]
    assert alert["impact"] == {"level": "low", "score": 4,
                               "reason": "Low - 4: front-desk check-in on RECEPTION-PC (front_desk account)"}


def test_device_strip_carries_impact(actions_h):
    actions_h.reset()
    actions_h.inject("password_guessing")     # RECEPTION-PC flips to under_attack
    device = [d for d in actions_h.get("/devices").json()["devices"]
              if d["agent_name"] == "RECEPTION-PC"][0]
    assert device["impact"] is not None and device["impact"]["level"] == "low"


# --- T7.06: the drill results weigh a missed step by its impact --------------------

def test_top_missed_impact(tmp_path):
    from drills import scoring
    book = _book(tmp_path)
    scenario = {"steps": [
        {"step_id": "s1", "phase": "detect", "devices": {"DOCTOR-PC": "infected"},
         "options": {"staff": [{"id": "a", "correct": True, "actions": ["ISOLATE_NETWORK"]},
                                {"id": "b", "correct": False, "actions": []}],
                     "owner": []}}]}
    players = [{"player_id": 1, "name": "Meena", "role": "front_desk"},
               {"player_id": 2, "name": "Ravi", "role": "front_desk"}]
    answers = [{"player_id": 1, "step_id": "s1", "option_id": "b", "correct": 0, "action_ids": []},
               {"player_id": 2, "step_id": "s1", "option_id": "a", "correct": 1,
                "action_ids": ["ISOLATE_NETWORK"]}]
    devices = [_dev("DOCTOR-PC", services=["Consultations"])]
    results = scoring.results(scenario, players, answers, host_player_id=None,
                              book=book, devices=devices)
    r = {p["name"]: p for p in results["players"]}
    # step_exposure is services x damage (no account): 3 (consultations) x 2 (infected) = 6.
    assert r["Meena"]["top_missed_impact"] == 6
    assert r["Ravi"]["top_missed_impact"] is None         # he got the only step right


def test_top_missed_impact_is_null_without_a_book(tmp_path):
    from drills import scoring
    scenario = {"steps": [
        {"step_id": "s1", "phase": "detect", "devices": {"DOCTOR-PC": "infected"},
         "options": {"staff": [{"id": "a", "correct": True, "actions": []}]}}]}
    players = [{"player_id": 1, "name": "Meena", "role": "front_desk"}]
    answers = []
    results = scoring.results(scenario, players, answers, host_player_id=None)
    assert results["players"][0]["top_missed_impact"] is None
