"""API tests for the contract v2 additions the new frontend needs: step ticking, "That was me"
and reopen, the IT support loop, ending a drill early, the current-drill lookup and skip-ahead.

Replay gives two password clicks (8 then 12 failures from 192.168.1.57 on RECEPTION-PC) and
one ransomware click (owner-only card on FILE-SERVER).
"""
import sqlite3

import pytest

OWNER, MEENA, RAVI = 3, 1, 2


def _pw_alert(h, role="front_desk"):
    h.reset()
    h.inject("password_guessing")
    return h.get(f"/alerts?role={role}").json()["alerts"][0]


def _step(alert, action):
    return next(s for s in alert["card"]["steps"] if s["action"] == action)


def _devices(h):
    return {d["agent_name"]: d["status"] for d in h.get("/devices").json()["devices"]}


# --- step ticking -----------------------------------------------------------------

def test_new_alert_has_nothing_ticked_and_no_it_activity(app_h):
    a = _pw_alert(app_h)
    assert all(s["done"] is False and s["done_by"] is None for s in a["card"]["steps"])
    assert a["it"]["status"] == "none" and a["it"]["log"] == []
    assert (a["reopened"], a["mine_by"], a["can_say_mine"]) == (False, None, True)


def test_tick_is_shared_across_roles_and_keeps_the_first_ticker(app_h):
    a = _pw_alert(app_h)
    app_h.clock.advance(30)
    r = app_h.put(f"/alerts/{a['id']}/steps/CALL_SAVED_IT", json={"staff_id": MEENA, "done": True})
    assert r.status_code == 200, r.text
    first = _step(r.json(), "CALL_SAVED_IT")
    assert first["done"] and first["done_by"] == MEENA and first["done_at"] == "2026-11-01T04:00:30Z"
    # The owner's card has CALL_SAVED_IT too, and shows it ticked.
    owner = app_h.get("/alerts?role=owner").json()["alerts"][0]
    assert _step(owner, "CALL_SAVED_IT")["done_by"] == MEENA
    # The owner ticks it again later: nothing changes, Meena stays the one who did it.
    app_h.clock.advance(30)
    again = app_h.put(f"/alerts/{a['id']}/steps/CALL_SAVED_IT", json={"staff_id": OWNER, "done": True}).json()
    # (The owner's step has its own wording; who ticked it and when must be unchanged.)
    tick = lambda s: (s["done"], s["done_by"], s["done_at"])
    assert tick(_step(again, "CALL_SAVED_IT")) == tick(first)
    # Ravi can't tick it at all: RECEPTION-PC isn't his computer, so for him the alert doesn't exist.
    r = app_h.put(f"/alerts/{a['id']}/steps/CALL_SAVED_IT", json={"staff_id": RAVI, "done": True})
    assert (r.status_code, r.json()["error"]) == (404, "not_found")


def test_untick_clears_the_step(app_h):
    a = _pw_alert(app_h)
    app_h.put(f"/alerts/{a['id']}/steps/DONT_USE_DEVICE", json={"staff_id": MEENA, "done": True})
    out = app_h.put(f"/alerts/{a['id']}/steps/DONT_USE_DEVICE", json={"staff_id": MEENA, "done": False}).json()
    assert _step(out, "DONT_USE_DEVICE") == {**_step(a, "DONT_USE_DEVICE"), "done": False}


def test_tick_errors(app_h):
    a = _pw_alert(app_h)
    # VERIFY_BACKUP is a real action ID but not on the front desk's password card.
    r = app_h.put(f"/alerts/{a['id']}/steps/VERIFY_BACKUP", json={"staff_id": MEENA, "done": True})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")
    r = app_h.put(f"/alerts/{a['id']}/steps/NOT_AN_ACTION", json={"staff_id": MEENA, "done": True})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")
    r = app_h.put("/alerts/999/steps/CALL_SAVED_IT", json={"staff_id": MEENA, "done": True})
    assert (r.status_code, r.json()["error"]) == (404, "not_found")
    r = app_h.put(f"/alerts/{a['id']}/steps/CALL_SAVED_IT", json={"staff_id": 99, "done": True})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")


def test_ticking_call_it_starts_the_it_loop(app_h):
    a = _pw_alert(app_h)
    out = app_h.put(f"/alerts/{a['id']}/steps/CALL_SAVED_IT", json={"staff_id": MEENA, "done": True}).json()
    assert out["it"]["status"] == "called" and out["it"]["called_by"] == MEENA
    assert [e["kind"] for e in out["it"]["log"]] == ["called"]
    # Unticking takes the "called" state back (the history line stays).
    out = app_h.put(f"/alerts/{a['id']}/steps/CALL_SAVED_IT", json={"staff_id": MEENA, "done": False}).json()
    assert out["it"]["status"] == "none" and len(out["it"]["log"]) == 1


# --- "That was me" and reopen ----------------------------------------------------------

def test_mine_pauses_the_alert_withdraws_the_block_and_tells_the_owner(actions_h):
    h = actions_h
    a = _pw_alert(h)
    assert a["action"]["status"] == "proposed" and _devices(h)["RECEPTION-PC"] == "under_attack"
    out = h.post(f"/alerts/{a['id']}/mine", json={"staff_id": MEENA}).json()
    assert (out["status"], out["mine_by"], out["action"]["status"]) == ("mine", MEENA, "withdrawn")
    assert _devices(h)["RECEPTION-PC"] == "ok"
    notes = h.get("/notifications?role=owner").json()["notifications"]
    assert "Meena says the alert on RECEPTION-PC was their own mistyping" in notes[-1]["text"]
    # The standing rule can no longer act on the withdrawn request.
    h.put("/clinic/standing-rule", json={"enabled": True, "staff_id": OWNER})
    h.advance(301)
    assert h.tick()["executed"] == 0
    # A second tap changes nothing.
    assert h.post(f"/alerts/{a['id']}/mine", json={"staff_id": MEENA}).json() == out


def test_mine_only_where_the_lesson_allows_it(app_h):
    app_h.reset()
    app_h.inject("ransomware")
    rw = app_h.get("/alerts?role=owner").json()["alerts"][0]
    assert rw["can_say_mine"] is False
    r = app_h.post(f"/alerts/{rw['id']}/mine", json={"staff_id": OWNER})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")


def test_mine_needs_an_open_alert(app_h):
    a = _pw_alert(app_h)
    app_h.post(f"/alerts/{a['id']}/done", json={"staff_id": MEENA})
    r = app_h.post(f"/alerts/{a['id']}/mine", json={"staff_id": MEENA})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")


def test_repeat_within_the_hour_reopens_the_same_card(actions_h):
    h = actions_h
    a = _pw_alert(h)
    h.post(f"/alerts/{a['id']}/mine", json={"staff_id": MEENA})
    h.advance(20 * 60)
    r = h.inject("password_guessing")                  # click 2: 12 failures
    assert (r["cards_created"], r["grouped"]) == (0, 1)
    alerts = h.get("/alerts?role=front_desk").json()["alerts"]
    assert len(alerts) == 1
    back = alerts[0]
    assert (back["id"], back["status"], back["reopened"], back["count"]) == (a["id"], "new", True, 12)
    # A fresh block request replaces the withdrawn one, and the PC is under attack again.
    assert back["action"]["status"] == "proposed" and back["action"]["id"] != a["action"]["id"]
    assert _devices(h)["RECEPTION-PC"] == "under_attack"
    assert "It happened again after Meena said" in h.get("/notifications?role=owner").json()["notifications"][-1]["text"]


def test_repeat_after_the_hour_is_a_new_card(app_h):
    a = _pw_alert(app_h)
    app_h.post(f"/alerts/{a['id']}/mine", json={"staff_id": MEENA})
    app_h.advance(61 * 60)
    assert app_h.inject("password_guessing")["cards_created"] == 1
    statuses = sorted(x["status"] for x in app_h.get("/alerts?role=front_desk").json()["alerts"])
    assert statuses == ["mine", "new"]


def test_staff_can_reopen_a_paused_alert(actions_h):
    h = actions_h
    a = _pw_alert(h)
    r = h.post(f"/alerts/{a['id']}/reopen", json={"staff_id": MEENA})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")       # not paused yet
    h.post(f"/alerts/{a['id']}/mine", json={"staff_id": MEENA})
    out = h.post(f"/alerts/{a['id']}/reopen", json={"staff_id": MEENA}).json()
    assert (out["status"], out["reopened"], out["action"]["status"]) == ("new", True, "proposed")
    assert [e["data"]["trigger"] for e in h.events("alert.reopened")] == ["staff"]


def test_reopen_does_not_ask_again_while_a_block_protects_the_pc(actions_h):
    h = actions_h
    a = _pw_alert(h)
    h.post(f"/actions/{a['action']['id']}/approve", json={"staff_id": OWNER})
    # Status is "new" with an executed block; force the pause to reach the reopen path.
    h.ctx.db.execute("UPDATE alerts SET status = 'mine', mine_by = 1, mine_at = '2026-11-01T04:00:00Z'")
    out = h.post(f"/alerts/{a['id']}/reopen", json={"staff_id": MEENA}).json()
    assert out["action"]["status"] == "executed"


# --- the IT support loop ------------------------------------------------------------

def test_it_loop_called_received_resolved_confirmed(actions_h):
    h = actions_h
    a = _pw_alert(h)
    aid = a["id"]
    h.put(f"/alerts/{aid}/steps/CALL_SAVED_IT", json={"staff_id": MEENA, "done": True})
    h.advance(60)
    got = h.post(f"/alerts/{aid}/it", json={"action": "received", "note": ""}).json()
    assert got["it"]["status"] == "received" and got["it"]["received_at"] == "2026-11-01T04:01:00Z"
    # The response is in the owner's wording: the IT panel shows the owner's card.
    assert got["card"]["headline"].startswith("Repeated password guessing")
    # A second "received" keeps the first time.
    h.advance(60)
    assert h.post(f"/alerts/{aid}/it", json={"action": "received", "note": ""}).json()["it"]["received_at"] == got["it"]["received_at"]
    h.post(f"/alerts/{aid}/it", json={"action": "note", "note": "Checking the router's client list."})
    res = h.post(f"/alerts/{aid}/it", json={"action": "resolved", "note": "Blocked the device and reset passwords."}).json()
    assert res["it"]["status"] == "resolved" and res["it"]["resolved_note"] == "Blocked the device and reset passwords."
    assert "says it's fixed" in h.get("/notifications?role=owner").json()["notifications"][-1]["text"]

    closed = h.post(f"/alerts/{aid}/close", json={"staff_id": OWNER, "confirm": True, "note": ""}).json()
    assert closed["it"]["status"] == "closed" and closed["it"]["closed_by"] == OWNER
    assert [e["kind"] for e in closed["it"]["log"]] == ["called", "received", "note", "resolved", "confirmed"]
    assert [e["by_staff_id"] for e in closed["it"]["log"]] == [MEENA, None, None, None, OWNER]
    # Closing withdraws the waiting block request and puts the PC back to OK.
    assert closed["action"]["status"] == "withdrawn" and _devices(h)["RECEPTION-PC"] == "ok"
    # Closed incidents leave the default list but stay readable.
    assert h.get("/alerts?role=owner").json()["alerts"] == []
    assert [x["id"] for x in h.get("/alerts?role=owner&include_closed=true").json()["alerts"]] == [aid]


def test_owner_can_send_it_back(app_h):
    a = _pw_alert(app_h)
    aid = a["id"]
    app_h.post(f"/alerts/{aid}/it", json={"action": "resolved", "note": "Changed the password."})
    back = app_h.post(f"/alerts/{aid}/close", json={"staff_id": OWNER, "confirm": False,
                                                    "note": "Reception still can't log in"}).json()
    it = back["it"]
    assert (it["status"], it["resolved_at"], it["sent_back_note"]) == ("received", None, "Reception still can't log in")
    # An empty reason gets the default wording.
    app_h.post(f"/alerts/{aid}/it", json={"action": "resolved", "note": "Fixed the login too."})
    assert app_h.post(f"/alerts/{aid}/close", json={"staff_id": OWNER, "confirm": False, "note": "  "}).json()["it"]["sent_back_note"] == "Not fixed yet"


def test_it_loop_errors(app_h):
    a = _pw_alert(app_h)
    aid = a["id"]
    r = app_h.post(f"/alerts/{aid}/it", json={"action": "note", "note": "  "})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")
    r = app_h.post(f"/alerts/{aid}/it", json={"action": "resolved", "note": "ok"})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")
    r = app_h.post(f"/alerts/{aid}/it", json={"action": "resolved", "note": "x" * 301})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")
    r = app_h.post(f"/alerts/{aid}/close", json={"staff_id": OWNER, "confirm": True, "note": ""})
    assert (r.status_code, r.json()["error"]) == (409, "not_resolved")
    app_h.post(f"/alerts/{aid}/it", json={"action": "resolved", "note": "Changed the password."})
    r = app_h.post(f"/alerts/{aid}/close", json={"staff_id": MEENA, "confirm": True, "note": ""})
    assert (r.status_code, r.json()["error"]) == (403, "not_owner")
    app_h.post(f"/alerts/{aid}/close", json={"staff_id": OWNER, "confirm": True, "note": ""})
    for path, body in ((f"/alerts/{aid}/it", {"action": "note", "note": "late"}),
                       (f"/alerts/{aid}/close", {"staff_id": OWNER, "confirm": True, "note": ""})):
        r = app_h.post(path, json=body)
        assert (r.status_code, r.json()["error"]) == (409, "already_closed")
    r = app_h.put(f"/alerts/{aid}/steps/CALL_SAVED_IT", json={"staff_id": MEENA, "done": True})
    assert (r.status_code, r.json()["error"]) == (409, "already_closed")


def test_a_new_attack_after_closing_is_a_new_card(app_h):
    a = _pw_alert(app_h)
    app_h.post(f"/alerts/{a['id']}/it", json={"action": "resolved", "note": "Changed the password."})
    app_h.post(f"/alerts/{a['id']}/close", json={"staff_id": OWNER, "confirm": True, "note": ""})
    assert app_h.inject("password_guessing")["cards_created"] == 1


def test_it_events_never_carry_note_text(app_h):
    a = _pw_alert(app_h)
    app_h.post(f"/alerts/{a['id']}/it", json={"action": "resolved", "note": "Secret detail 192.168.1.57"})
    app_h.post(f"/alerts/{a['id']}/close", json={"staff_id": OWNER, "confirm": False, "note": "Secret reason"})
    for e in app_h.events("alert."):
        assert "Secret" not in str(e["data"])
    assert [e["data"] for e in app_h.events("alert.it")] == [{"it_action": "resolved"}]
    assert [e["data"] for e in app_h.events("alert.closed")] == [{"confirmed": False}]


# --- drills: current and end -----------------------------------------------------------

def _drill(h):
    r = h.post("/drills", json={"scenario_id": "ransomware_clinic", "host_staff_id": OWNER, "source_alert_id": None})
    code, host = r.json()["code"], r.json()["player_id"]
    meena = h.post(f"/drills/{code}/join", json={"staff_id": MEENA}).json()["player_id"]
    return code, host, meena


def test_current_drill(app_h):
    app_h.reset()
    assert app_h.get("/drills/current").json() == {"drill": None}
    code, host, _ = _drill(app_h)
    assert app_h.get("/drills/current").json()["drill"] == {
        "code": code, "scenario_id": "ransomware_clinic", "title": "Ransomware at the clinic", "status": "lobby"}
    app_h.post(f"/drills/{code}/end", json={"player_id": host})
    assert app_h.get("/drills/current").json() == {"drill": None}


def test_lobby_lists_who_has_joined(app_h):
    app_h.reset()
    code, host, meena = _drill(app_h)
    team = app_h.get(f"/drills/{code}?player_id={meena}").json()["team"]
    assert [(p["name"], p["has_options"], p["answered"]) for p in team["players"]] == [
        ("Dr. Rao", False, False), ("Meena", False, False)]
    assert (team["answered"], team["total"]) == (0, 0)


def test_host_ends_a_drill_midway(app_h):
    app_h.reset()
    code, host, meena = _drill(app_h)
    app_h.post(f"/drills/{code}/advance", json={"player_id": host})          # open s1
    app_h.post(f"/drills/{code}/answers", json={"player_id": meena, "step_id": "s1", "option_id": "b"})
    r = app_h.post(f"/drills/{code}/end", json={"player_id": meena})
    assert (r.status_code, r.json()["error"]) == (403, "not_host")
    view = app_h.post(f"/drills/{code}/end", json={"player_id": host}).json()
    assert view["status"] == "finished" and view["results"] is not None and view["can_advance"] is False
    # Only the moment the team reached is scored.
    assert view["results"]["team"] == {"correct": 1, "total": 1}
    r = app_h.post(f"/drills/{code}/end", json={"player_id": host})
    assert (r.status_code, r.json()["error"]) == (409, "drill_finished")
    assert [e["data"] for e in app_h.events("drill.ended")] == [{"from_status": "review", "step_index": 0}]


def test_end_in_the_lobby_scores_nothing(app_h):
    app_h.reset()
    code, host, _ = _drill(app_h)
    view = app_h.post(f"/drills/{code}/end", json={"player_id": host}).json()
    assert view["results"]["team"] == {"correct": 0, "total": 0} and view["impact"] == []


def test_end_while_open_counts_unanswered_as_missed(app_h):
    app_h.reset()
    code, host, meena = _drill(app_h)
    app_h.post(f"/drills/{code}/join", json={"staff_id": RAVI})
    app_h.post(f"/drills/{code}/advance", json={"player_id": host})          # open s1
    app_h.post(f"/drills/{code}/answers", json={"player_id": meena, "step_id": "s1", "option_id": "b"})
    view = app_h.post(f"/drills/{code}/end", json={"player_id": host}).json()  # Ravi never answered
    assert view["results"]["team"] == {"correct": 1, "total": 2}


def test_end_unknown_drill(app_h):
    app_h.reset()
    r = app_h.post("/drills/0000/end", json={"player_id": 1})
    assert (r.status_code, r.json()["error"]) == (404, "drill_not_found")


# --- skip ahead -----------------------------------------------------------------------

def test_skip_lets_the_standing_rule_act_and_reset_puts_the_clock_back(actions_h):
    h = actions_h
    a = _pw_alert(h)
    h.put("/clinic/standing-rule", json={"enabled": True, "staff_id": OWNER})
    r = h.post("/demo/skip", json={"minutes": 5})
    assert r.json() == {"offset_minutes": 5, "server_time": "2026-11-01T04:05:00Z"}
    # The timeout pass ran during the skip, so the block is already in place.
    action = h.get("/actions").json()["actions"][0]
    assert (action["id"], action["status"], action["decided_via"]) == (a["action"]["id"], "executed", "standing_rule")
    assert h.post("/demo/skip", json={"minutes": 5}).json()["offset_minutes"] == 10
    assert h.reset()["reset_at"] == "2026-11-01T04:00:00Z"
    assert [e["data"] for e in h.events("demo.skip")] == [{"minutes": 5, "offset_minutes": 5},
                                                           {"minutes": 5, "offset_minutes": 10}]


def test_reset_after_the_standing_rule_blocked(actions_h):
    """Regression: the standing rule's notification points at its action, and Reset used to
    delete actions before notifications, failing on the foreign key."""
    h = actions_h
    _pw_alert(h)
    h.put("/clinic/standing-rule", json={"enabled": True, "staff_id": OWNER})
    h.advance(301)
    assert h.tick()["executed"] == 1
    h.reset()
    assert h.get("/actions").json()["actions"] == []


@pytest.mark.parametrize("minutes", [0, 121, -5])
def test_skip_range(app_h, minutes):
    r = app_h.post("/demo/skip", json={"minutes": minutes})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")


def test_skip_needs_the_backstage_token_once_set(make_app):
    h = make_app(backstage_token="s3cret")
    assert h.post("/demo/skip", json={"minutes": 5}).json()["error"] == "pin_required"
    ok = h.post("/demo/skip", json={"minutes": 5}, headers={"X-Backstage-Token": "s3cret"})
    assert ok.status_code == 200


# --- schema upgrade -----------------------------------------------------------------------

def test_an_older_database_file_is_rebuilt(tmp_path):
    """A v1 file (no user_version, old CHECK constraints) is rebuilt and re-seeded at start-up."""
    from config import Config
    from db import SCHEMA_VERSION, connect

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE clinic (id INTEGER PRIMARY KEY, name TEXT);"
                       "INSERT INTO clinic VALUES (1, 'old');"
                       "CREATE TABLE alerts (id INTEGER PRIMARY KEY, status TEXT CHECK (status IN ('new')));")
    conn.close()
    db = connect(Config(db_path=path, restore_sandbox_dir=tmp_path / "sandbox"))
    try:
        assert db.clinic()["name"] == "Sunrise Family Clinic"
        assert db.one("PRAGMA user_version")[0] == SCHEMA_VERSION
        assert db.one("SELECT 1 FROM sqlite_master WHERE name = 'alert_it_log'") is not None
    finally:
        db.close()
