"""T4.06-T4.08 via FakeClock: standing-rule timeout, escalation, and block expiry."""
import pytest

from actions import propose

OWNER = 3
RAVI = 2


@pytest.fixture
def h(make_app):
    h = make_app(actions=True)
    h.reset()
    h.inject("password_guessing")
    return h


def only_action(h):
    return h.get("/actions").json()["actions"][0]


def test_nothing_happens_before_five_minutes(h):
    h.advance(299)
    assert h.tick() == {"executed": 0, "escalated": 0, "expired": 0}
    assert only_action(h)["status"] == "proposed"


def test_t4_06_standing_rule_on_executes_after_five_minutes(h):
    h.put("/clinic/standing-rule", json={"enabled": True, "staff_id": OWNER})
    assert only_action(h)["on_timeout"] == "block_under_standing_rule"
    h.advance(301)
    assert h.tick()["executed"] == 1
    a = only_action(h)
    assert (a["status"], a["decided_via"], a["decided_by"], a["simulated"]) == ("executed", "standing_rule", OWNER, True)
    note = h.get("/notifications?role=owner").json()["notifications"][-1]
    assert note["text"] == "Blocked under your standing rule." and note["action_row_id"] == a["id"]
    assert h.wazuh.calls == []                       # replayed alert: simulated, nothing sent


def test_t4_07_standing_rule_off_asks_backup_approver_once(h):
    h.advance(301)
    assert h.tick()["escalated"] == 1
    assert only_action(h)["status"] == "proposed"    # not executed
    notes = h.get(f"/notifications?staff_id={RAVI}").json()["notifications"]
    assert len(notes) == 1 and "Dr. Rao hasn't answered" in notes[0]["text"] and "+91 90000 00000" in notes[0]["text"]
    h.advance(30)
    assert h.tick()["escalated"] == 0                # only once
    assert len(h.get(f"/notifications?staff_id={RAVI}").json()["notifications"]) == 1


def test_t4_08_block_expires_after_an_hour_and_device_goes_ok(h, monkeypatch):
    statuses = []
    import routes.devices as devices
    monkeypatch.setattr(devices, "set_device_status", lambda db, name, st, when: statuses.append((name, st)), raising=False)
    aid = only_action(h)["id"]
    assert h.post(f"/actions/{aid}/approve", json={"staff_id": OWNER}).json()["status"] == "executed"
    h.advance(59 * 60)
    assert h.tick()["expired"] == 0
    h.advance(61)
    assert h.tick()["expired"] == 1
    assert only_action(h)["status"] == "expired"
    assert statuses[-2:] == [("RECEPTION-PC", "protected"), ("RECEPTION-PC", "ok")]


def test_live_alert_standing_rule_calls_the_client(make_app):
    """A non-simulated action (source wazuh) does reach the client under the standing rule."""
    h = make_app(actions=True)
    h.reset()
    h.ctx.db.execute(
        "INSERT INTO alerts (id,source,rule_id,level,agent_name,group_key,lesson_id,status,raw,first_seen,last_seen)"
        " VALUES (50,'wazuh','60204',10,'RECEPTION-PC','60204:RECEPTION-PC','password_guessing','new','{}','t','t')")
    propose.propose(h.ctx.db, h.clock, 50, "wazuh", "RECEPTION-PC", "192.168.1.57")
    h.put("/clinic/standing-rule", json={"enabled": True, "staff_id": OWNER})
    h.advance(301)
    h.tick()
    assert h.wazuh.calls == [("block_ip", "003", "192.168.1.57")]
