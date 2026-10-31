"""Who gets which alert (alerts/notify.audience), over HTTP.

The rules:
- Ravi (billing) never gets an alert on RECEPTION-PC, Meena's computer: no card, no notification.
- Meena (front desk) never gets an alert on FILE-SERVER, Ravi's computer.
- The owner always does, and so does the IT contact, whose panel lists the owner's cards.
- Whoever sees a card also gets its attack notification, and nobody else does.
- Nobody can act on (tick, Done, "That was me", reopen, reword) an alert they can't see.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

from alerts import pipeline
from alerts.normalise import normalise

OWNER, MEENA, RAVI = 3, 1, 2
STAFF_BY_ROLE = {"front_desk": MEENA, "billing": RAVI, "owner": OWNER}
ROLES = ("front_desk", "billing", "owner")
BACKEND = Path(__file__).resolve().parents[2]
LESSONS = json.loads((BACKEND / "lessons" / "lessons.json").read_text())
RULES = [lesson["rule_id"] for lesson in LESSONS]
DEVICES = ("RECEPTION-PC", "FILE-SERVER", "DOCTOR-PC", "NEW-LAPTOP")     # the last one isn't in the seed

# Who each alert reaches on the computer the demo fires it on (replay/alerts.json, replay/sim/*.json).
DEMO = {
    ("60204", "RECEPTION-PC"): {"front_desk", "owner"},              # password guessing
    ("100201", "FILE-SERVER"): {"owner"},                            # ransomware: owner-only card
    ("61320", "DOCTOR-PC"): {"owner"},                               # phishing in the doctor's inbox
    ("100310", "DOCTOR-PC"): {"owner"},                              # doctor's email taken over
    ("100311", "DOCTOR-PC"): {"front_desk", "billing", "owner"},     # fake fee emails to patients
    ("100320", "RECEPTION-PC"): {"front_desk", "owner"},             # remote-control program installed
    ("100321", "RECEPTION-PC"): {"front_desk", "owner"},             # remote control in use
    ("100322", "RECEPTION-PC"): {"front_desk", "owner"},             # files copied out
    ("100330", "FILE-SERVER"): {"billing", "owner"},                 # supplier asks for new bank details
    ("100331", "FILE-SERVER"): {"billing", "owner"},                 # payment to the new account
}
# The same rules on other computers (live mode can fire them anywhere).
ELSEWHERE = {
    ("60204", "FILE-SERVER"): {"billing", "owner"},
    ("60204", "DOCTOR-PC"): {"owner"},
    ("61320", "RECEPTION-PC"): {"front_desk", "owner"},
    ("61320", "FILE-SERVER"): {"billing", "owner"},
    ("100330", "RECEPTION-PC"): {"owner"},                           # never Ravi on the reception PC
    ("100311", "RECEPTION-PC"): {"front_desk", "owner"},
    ("100311", "FILE-SERVER"): {"billing", "owner"},
    ("60204", "NEW-LAPTOP"): {"owner"},
}


def _fire(h, rule_id: str, agent: str) -> None:
    """Store one alert for ``rule_id`` on ``agent``, the way ingest does."""
    raw = {"source": "replay", "external_id": None, "shieldmate": None, "alert": {
        "rule": {"id": rule_id, "level": 12}, "agent": {"name": agent},
        "data": {"win": {"eventdata": {"targetUserName": "u", "ipAddress": "203.0.113.9"}}},
        "mail": {"from": "someone@example.in"}}}
    assert pipeline.process(normalise(raw, "2026-11-01T04:00:00Z"), h.ctx.db, h.clock,
                            lessons=h.ctx.lessons, config=h.config) == "created"


def _cards(h, role):
    return h.get(f"/alerts?role={role}").json()["alerts"]


def _attack_notes(h, role):
    notes = h.get("/notifications", params={"role": role, "staff_id": STAFF_BY_ROLE[role]}).json()["notifications"]
    return [n for n in notes if n["kind"] == "attack"]


def _reached(h) -> set[str]:
    """The roles with a card, after checking each card-holder also got the notification (and only they did)."""
    with_card = {r for r in ROLES if _cards(h, r)}
    notified = {r for r in ROLES if _attack_notes(h, r)}
    assert with_card == notified, f"cards {with_card} but notifications {notified}"
    return with_card


# --- the table --------------------------------------------------------------------------

@pytest.mark.parametrize(("rule", "agent"), list(DEMO))
def test_each_demo_alert_reaches_exactly_the_right_people(actions_h, rule, agent):
    actions_h.reset()
    _fire(actions_h, rule, agent)
    assert _reached(actions_h) == DEMO[(rule, agent)]


@pytest.mark.parametrize(("rule", "agent"), list(ELSEWHERE))
def test_the_same_rules_on_other_computers_follow_the_computer(actions_h, rule, agent):
    actions_h.reset()
    _fire(actions_h, rule, agent)
    assert _reached(actions_h) == ELSEWHERE[(rule, agent)]


def test_the_table_covers_every_rule():
    assert {rule for rule, _ in DEMO} == set(RULES)


def test_the_demo_data_fires_each_rule_on_the_computer_the_table_expects():
    """If a replay or sim file moves a rule to another computer, the table above must change with it."""
    fired: dict[str, set[str]] = {}
    files = [BACKEND / "replay" / "alerts.json", *map(Path, glob.glob(str(BACKEND / "replay" / "sim" / "*.json")))]
    for path in files:
        data = json.loads(path.read_text())
        items = [x["alert"] for x in data] if isinstance(data, list) else [p["alert"] for p in data["phases"]]
        for alert in items:
            fired.setdefault(alert["rule"]["id"], set()).add(alert["agent"]["name"])
    for (rule, agent) in DEMO:
        assert fired.get(rule, {agent}) == {agent}, f"rule {rule} fires on {fired.get(rule)}"


# --- the invariants, for every rule on every computer ------------------------------------

@pytest.mark.parametrize("agent", DEVICES)
@pytest.mark.parametrize("rule", RULES)
def test_no_one_hears_about_another_staff_members_computer(actions_h, rule, agent):
    actions_h.reset()
    _fire(actions_h, rule, agent)
    reached = _reached(actions_h)
    if agent == "RECEPTION-PC":
        assert "billing" not in reached                  # Ravi never gets a reception-PC alert
    if agent == "FILE-SERVER":
        assert "front_desk" not in reached               # Meena never gets an alert on Ravi's computer
    # The owner always gets it, and so does the IT contact (the IT panel lists the owner's cards).
    assert "owner" in reached
    assert len(_cards(actions_h, "owner")) == 1


@pytest.mark.parametrize("agent", DEVICES)
@pytest.mark.parametrize("rule", RULES)
def test_only_the_people_who_see_it_can_act_on_it(make_app, rule, agent):
    h = make_app(ai_reword=True)
    h.reset()
    _fire(h, rule, agent)
    alert_id = _cards(h, "owner")[0]["id"]
    for role, staff_id in STAFF_BY_ROLE.items():
        mine = _cards(h, role)
        reword = h.post(f"/alerts/{alert_id}/reword", json={"role": role, "lang": "en"})
        if mine:
            step = mine[0]["card"]["steps"][0]["action"]
            assert h.put(f"/alerts/{alert_id}/steps/{step}", json={"staff_id": staff_id, "done": True}).status_code == 200
            assert reword.status_code == 200
            continue
        for method, path, body in (
                ("put", f"/alerts/{alert_id}/steps/CALL_SAVED_IT", {"staff_id": staff_id, "done": True}),
                ("post", f"/alerts/{alert_id}/done", {"staff_id": staff_id}),
                ("post", f"/alerts/{alert_id}/mine", {"staff_id": staff_id}),
                ("post", f"/alerts/{alert_id}/reopen", {"staff_id": staff_id})):
            r = getattr(h, method)(path, json=body)
            assert (r.status_code, r.json()["error"]) == (404, "not_found"), (role, path)
        assert (reword.status_code, reword.json()["error"]) == (404, "not_found")
    # Nobody outside the alert changed it: no step was ticked by them and it's still open.
    owner_card = _cards(h, "owner")[0]
    assert owner_card["status"] == "new"
    assert {s["done_by"] for s in owner_card["card"]["steps"] if s["done"]} <= {
        STAFF_BY_ROLE[r] for r in ROLES if _cards(h, r)}


# --- the replayed demo itself -----------------------------------------------------------

def test_the_password_replay_reaches_meena_and_the_owner_never_ravi(actions_h):
    h = actions_h
    h.reset()
    h.inject("password_guessing")
    assert [a["agent_name"] for a in _cards(h, "front_desk")] == ["RECEPTION-PC"]
    assert _cards(h, "billing") == []
    assert h.get("/notifications", params={"role": "billing", "staff_id": RAVI}).json()["notifications"] == []
    # Meena says "That was me", then it happens again: still nothing for Ravi.
    alert_id = _cards(h, "front_desk")[0]["id"]
    assert h.post(f"/alerts/{alert_id}/mine", json={"staff_id": MEENA}).status_code == 200
    h.inject("password_guessing")
    assert _cards(h, "front_desk")[0]["reopened"] is True
    assert _cards(h, "billing") == []
    assert h.get("/notifications", params={"role": "billing", "staff_id": RAVI}).json()["notifications"] == []


def test_ravi_cant_say_that_was_me_for_the_reception_pc(app_h):
    app_h.reset()
    app_h.inject("password_guessing")
    alert_id = _cards(app_h, "owner")[0]["id"]
    r = app_h.post(f"/alerts/{alert_id}/mine", json={"staff_id": RAVI})
    assert (r.status_code, r.json()["error"]) == (404, "not_found")
    assert _cards(app_h, "owner")[0]["status"] == "new"
    info = [n for n in app_h.get("/notifications?role=owner").json()["notifications"] if n["kind"] == "info"]
    assert info == []                                    # no "Ravi says it was his mistyping" note either


def test_the_ransomware_replay_reaches_only_the_owner(app_h):
    app_h.reset()
    app_h.inject("ransomware")
    assert _reached(app_h) == {"owner"}


# --- escalation: the backup approver gets a working Block button --------------------------

def test_the_escalation_to_ravi_has_a_block_button_that_works(actions_h):
    h = actions_h
    h.reset()
    h.inject("password_guessing")
    h.advance(301)
    assert h.tick()["escalated"] == 1
    notes = h.get("/notifications", params={"role": "billing", "staff_id": RAVI}).json()["notifications"]
    (note,) = notes                                       # only the escalation: no reception-PC card or alert note
    action = h.get("/actions").json()["actions"][0]
    assert note["kind"] == "info" and note["to_staff_id"] == RAVI and "RECEPTION-PC" in note["text"]
    assert note["quick_action"] == {
        "action_row_id": action["id"], "action": "BLOCK_IP", "label": action["label"],
        "target_ip": action["target_ip"], "minutes": 60, "status": "proposed"}
    assert _cards(h, "billing") == []                     # the card still isn't his
    # His tap approves the block, and the button follows it.
    assert h.post(f"/actions/{action['id']}/approve", json={"staff_id": RAVI}).status_code == 200
    note = h.get("/notifications", params={"role": "billing", "staff_id": RAVI}).json()["notifications"][0]
    assert note["quick_action"]["status"] == "executed"
    assert h.get("/actions").json()["actions"][0]["decided_by"] == RAVI


def test_the_escalation_button_goes_once_the_owner_declines(actions_h):
    h = actions_h
    h.reset()
    h.inject("password_guessing")
    h.advance(301)
    h.tick()
    action = h.get("/actions").json()["actions"][0]
    assert h.post(f"/actions/{action['id']}/decline", json={"staff_id": OWNER}).status_code == 200
    (note,) = h.get("/notifications", params={"staff_id": RAVI}).json()["notifications"]
    assert note["quick_action"] is None
    r = h.post(f"/actions/{action['id']}/approve", json={"staff_id": RAVI})
    assert (r.status_code, r.json()["error"]) == (409, "action_not_pending")
