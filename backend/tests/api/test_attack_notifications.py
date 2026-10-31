"""v3: a new alert card sends an "attack" notification with a Block button (quick_action).

The button is the existing BLOCK_IP proposal, fired with POST /actions/{id}/approve, so these tests
check that the note points at the right action and follows its status.
"""
from alerts import pipeline
from alerts.normalise import normalise

OWNER = 3


def notes(h, role):
    return h.get(f"/notifications?role={role}&since_id=0").json()["notifications"]


def attack_notes(h, role):
    return [n for n in notes(h, role) if n["kind"] == "attack"]


def test_a_new_password_attack_notifies_front_desk_and_owner_with_a_block_button(actions_h):
    h = actions_h
    h.reset(); h.inject("password_guessing")
    front, owner = attack_notes(h, "front_desk"), attack_notes(h, "owner")
    assert len(front) == 1 and len(owner) == 1 and notes(h, "billing") == []
    action = h.get("/actions").json()["actions"][0]
    for n in (front[0], owner[0]):
        assert n["action_row_id"] == action["id"] and n["from_staff"] is None
        assert n["quick_action"] == {
            "action_row_id": action["id"], "action": "BLOCK_IP", "label": action["label"],
            "target_ip": action["target_ip"], "minutes": 60, "status": "proposed"}
    assert front[0]["quick_action"]["label"] == f"Block {action['target_ip']} for 60 minutes"
    assert "guessing the password" in front[0]["text"]          # the role's own card headline


def test_the_button_follows_the_action_once_it_is_approved(actions_h):
    h = actions_h
    h.reset(); h.inject("password_guessing")
    aid = attack_notes(h, "front_desk")[0]["quick_action"]["action_row_id"]
    assert h.post(f"/actions/{aid}/approve", json={"staff_id": 1}).status_code == 200    # Meena taps it
    assert attack_notes(h, "front_desk")[0]["quick_action"]["status"] == "executed"
    assert attack_notes(h, "owner")[0]["quick_action"]["status"] == "executed"
    h.advance(61 * 60); h.tick()
    assert attack_notes(h, "front_desk")[0]["quick_action"]["status"] == "expired"


def test_with_actions_off_the_note_has_no_button(app_h):
    app_h.reset(); app_h.inject("password_guessing")
    front = attack_notes(app_h, "front_desk")
    assert len(front) == 1 and front[0]["action_row_id"] is None and front[0]["quick_action"] is None


def test_ransomware_notifies_only_the_owner_and_has_no_button(actions_h):
    h = actions_h
    h.reset(); h.inject("ransomware")
    assert notes(h, "billing") == [] and notes(h, "front_desk") == []        # the card is owner-only
    (owner,) = attack_notes(h, "owner")
    assert owner["quick_action"] is None and "ransomware" in owner["text"]


def test_a_repeat_of_the_same_alert_does_not_notify_again(actions_h):
    h = actions_h
    h.reset(); h.inject("password_guessing")
    first = notes(h, "front_desk")
    h.inject("password_guessing")                                             # grouped into the open card
    assert notes(h, "front_desk") == first and len(attack_notes(h, "owner")) == 1


def test_a_refused_target_gets_no_button(actions_h):
    h = actions_h
    h.reset()
    raw = {"source": "replay", "external_id": None, "shieldmate": None, "alert": {
        "rule": {"id": "60204", "level": 10}, "agent": {"name": "RECEPTION-PC"},
        "data": {"win": {"eventdata": {"targetUserName": "u", "ipAddress": "192.168.1.5"}}}}}   # the Wazuh server
    assert pipeline.process(normalise(raw, "2026-11-01T04:00:00Z"), h.ctx.db, h.clock,
                            lessons=h.ctx.lessons, config=h.config) == "created"
    (front,) = attack_notes(h, "front_desk")
    assert front["action_row_id"] is not None and front["quick_action"] is None


def test_an_info_note_that_points_at_an_action_never_gets_a_button(actions_h):
    h = actions_h
    h.reset(); h.inject("password_guessing")
    action = h.get("/actions").json()["actions"][0]
    h.ctx.db.add_notification("Your standing rule blocked it.", "2026-11-01T04:30:00Z",
                              action_row_id=action["id"], to_role="owner")
    info = [n for n in notes(h, "owner") if n["kind"] == "info"]
    assert len(info) == 1 and info[0]["action_row_id"] == action["id"] and info[0]["quick_action"] is None
