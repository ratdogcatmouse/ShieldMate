"""API tests for the drill story: T1.05, T1.07-T1.10, T1.16, T2.07, T4.11 over HTTP.

``POST /drills`` carries the owner dependency, but the PIN is off by default (decision 3),
so the routes are open - the tests just send the host's staff id in the body.
"""
import json

OWNER, MEENA, RAVI = 3, 1, 2


def _start(h, join=(MEENA, RAVI)):
    """Create a ransomware drill for the owner and join the phones; return code + player ids."""
    r = h.post("/drills", json={"scenario_id": "ransomware_clinic", "host_staff_id": OWNER,
                                 "source_alert_id": None})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    players = {OWNER: r.json()["player_id"]}
    for staff in join:
        j = h.post(f"/drills/{code}/join", json={"staff_id": staff})
        assert j.status_code == 200, j.text
        players[staff] = j.json()["player_id"]
    return code, players


# --- create / join ------------------------------------------------------------

def test_t1_05_create_and_join(app_h):
    app_h.reset()
    r = app_h.post("/drills", json={"scenario_id": "ransomware_clinic", "host_staff_id": OWNER,
                                     "source_alert_id": None})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "lobby"
    assert body["code"].isdigit() and len(body["code"]) == 4      # 4-digit code
    assert app_h.post("/drills", json={"scenario_id": "no_such_scenario",
                                        "host_staff_id": OWNER, "source_alert_id": None}).json()["error"] == "invalid_request"
    assert app_h.post("/drills", json={"scenario_id": "ransomware_clinic",
                                        "host_staff_id": 99, "source_alert_id": None}).json()["error"] == "invalid_request"
    join = app_h.post(f"/drills/{body['code']}/join", json={"staff_id": MEENA}).json()
    assert join["player_id"] and join["status"] == "lobby"
    # Decision 14: the same staff_id rejoins with the same player_id.
    assert app_h.post(f"/drills/{body['code']}/join", json={"staff_id": MEENA}).json()["player_id"] == join["player_id"]
    assert app_h.post("/drills/0000/join", json={"staff_id": MEENA}).json()["error"] == "drill_not_found"


def test_new_drill_code_never_reuses_a_finished_drills_code(app_h, monkeypatch):
    """The code is the primary key: a collision with a *finished* drill used to be a 500."""
    import random
    app_h.reset()
    codes = iter(["1234", "1234", "5678"])          # second draw collides, third is free
    monkeypatch.setattr(random, "randint", lambda a, b: int(next(codes)))
    code, players = _start(app_h, join=())
    assert code == "1234"
    for _ in range(9):                              # lobby, then open + review for each of the 4 steps
        app_h.post(f"/drills/{code}/advance", json={"player_id": players[OWNER]})
    assert app_h.get(f"/drills/{code}", params={"player_id": players[OWNER]}).json()["status"] == "finished"
    again = app_h.post("/drills", json={"scenario_id": "ransomware_clinic", "host_staff_id": OWNER,
                                         "source_alert_id": None})
    assert again.status_code == 200, again.text
    assert again.json()["code"] == "5678"


def test_practise_with_the_team_links_the_alert(app_h):
    app_h.reset()
    app_h.inject("password_guessing")
    aid = app_h.get("/alerts?role=owner").json()["alerts"][0]["id"]
    r = app_h.post("/drills", json={"scenario_id": "ransomware_clinic", "host_staff_id": OWNER,
                                     "source_alert_id": aid})
    assert r.status_code == 200
    assert app_h.ctx.db.one("SELECT source_alert_id FROM drills WHERE code = ?",
                            (r.json()["code"],))["source_alert_id"] == aid


# --- answers ------------------------------------------------------------------

def test_t1_07_t1_09_answers_over_the_wire(app_h):
    app_h.reset()
    code, players = _start(app_h)
    host = players[OWNER]
    assert app_h.post(f"/drills/{code}/advance", json={"player_id": host}).json()["status"] == "open"
    # A player who is not in the drill cannot answer.
    assert app_h.post(f"/drills/{code}/answers", json={"player_id": 99, "step_id": "s1", "option_id": "b"}).json()["error"] == "player_not_in_drill"
    # An option the role was not offered is invalid_option (the owner has no s1 options).
    r = app_h.post(f"/drills/{code}/answers", json={"player_id": host, "step_id": "s1", "option_id": "a"})
    assert (r.status_code, r.json()["error"]) == (400, "invalid_option")
    r = app_h.post(f"/drills/{code}/answers", json={"player_id": players[MEENA], "step_id": "s1", "option_id": "b"})
    assert r.status_code == 200 and r.json() == {"option_id": "b", "correct": True,
                                                  "feedback": "Right. Cutting the network stops the spread and keeps the evidence.",
                                                  "actions": ["ISOLATE_NETWORK"]}
    # A second answer to the same step is already_answered and changes nothing (T1.07).
    again = app_h.post(f"/drills/{code}/answers", json={"player_id": players[MEENA], "step_id": "s1", "option_id": "c"})
    assert (again.status_code, again.json()["error"]) == (409, "already_answered")
    v = app_h.get(f"/drills/{code}", params={"player_id": players[MEENA]}).json()
    assert v["my_answer"]["option_id"] == "b"                       # the first answer stands


def test_t1_08_late_answer_is_step_closed(app_h):
    app_h.reset()
    code, players = _start(app_h, join=(MEENA,))
    host = players[OWNER]
    app_h.post(f"/drills/{code}/advance", json={"player_id": host})             # open s1
    app_h.post(f"/drills/{code}/answers", json={"player_id": players[MEENA], "step_id": "s1", "option_id": "b"})
    # Everyone with options has answered: the step auto-closed to review (T1.10).
    assert app_h.get(f"/drills/{code}", params={"player_id": host}).json()["status"] == "review"
    r = app_h.post(f"/drills/{code}/answers", json={"player_id": host, "step_id": "s1", "option_id": "b"})
    assert (r.status_code, r.json()["error"]) == (409, "step_closed")


# --- the T1.11 scripted run, over the wire ------------------------------------

def test_t1_11_t2_07_scripted_results(app_h):
    app_h.reset()
    code, p = _start(app_h)
    host, meena, ravi = p[OWNER], p[MEENA], p[RAVI]

    def answer(pid, step, opt):
        app_h.post(f"/drills/{code}/answers", json={"player_id": pid, "step_id": step, "option_id": opt})

    def advance(status):
        r = app_h.post(f"/drills/{code}/advance", json={"player_id": host})
        assert r.status_code == 200 and r.json()["status"] == status, r.text

    # s1/s2 have no owner options, so each auto-closes to review the moment both staff
    # answer; only s3/s4 (owner options) need the host's answer to close.
    advance("open")                                   # s1 open
    answer(meena, "s1", "b"); answer(ravi, "s1", "c") # -> auto-closes s1 to review
    advance("open")                                   # s2 open
    answer(meena, "s2", "b"); answer(ravi, "s2", "a") # -> auto-closes s2 to review
    advance("open")                                   # s3 open
    answer(meena, "s3", "a"); answer(ravi, "s3", "a"); answer(host, "s3", "b")
    assert app_h.get(f"/drills/{code}", params={"player_id": host}).json()["restore_check_available"] is True
    advance("open")                                   # s4 open
    answer(meena, "s4", "a"); answer(ravi, "s4", "a"); answer(host, "s4", "b")
    advance("finished")

    r = app_h.get(f"/drills/{code}", params={"player_id": host}).json()["results"]
    by = {x["name"]: x for x in r["players"]}
    # No host row (the host runs the drill); only Meena and Ravi are scored.
    assert set(by) == {"Meena", "Ravi"}
    assert by["Meena"]["missed_actions"] == []
    assert by["Ravi"]["missed_actions"] == ["ISOLATE_NETWORK", "CALL_SAVED_IT", "NOTIFY_OWNER"]
    assert r["team"] == {"correct": 8, "total": 10}      # the frozen finished view's score
    assert r["restore"] is None
    # A finished drill is finished: no more joins, answers or advances.
    assert app_h.post(f"/drills/{code}/join", json={"staff_id": MEENA}).json()["error"] == "drill_finished"
    assert app_h.post(f"/drills/{code}/advance", json={"player_id": host}).json()["error"] == "drill_finished"
    assert app_h.post(f"/drills/{code}/answers", json={"player_id": meena, "step_id": "s1", "option_id": "a"}).json()["error"] == "drill_finished"


def test_t4_11_block_ip_drill_option_never_proposes(app_h):
    app_h.reset()
    created = app_h.post("/drills", json={"scenario_id": "password_guessing",
                                           "host_staff_id": OWNER, "source_alert_id": None}).json()
    code, host = created["code"], created["player_id"]
    app_h.post(f"/drills/{code}/advance", json={"player_id": host})
    app_h.post(f"/drills/{code}/advance", json={"player_id": host})
    app_h.post(f"/drills/{code}/advance", json={"player_id": host})        # open s2 (BLOCK_IP option)
    r = app_h.post(f"/drills/{code}/answers", json={"player_id": host, "step_id": "s2", "option_id": "a"})
    assert r.status_code == 200 and r.json()["option_id"] == "a"           # the BLOCK_IP option, for real
    assert app_h.ctx.db.one("SELECT count(*) AS n FROM actions")["n"] == 0


# --- review panel and drill-finished view (fixture-anchored) ------------------

def test_review_panel_over_the_wire(app_h):
    app_h.reset()
    code, p = _start(app_h)                    # host + Meena + Ravi
    host = p[OWNER]
    app_h.post(f"/drills/{code}/advance", json={"player_id": host})             # open s1
    app_h.post(f"/drills/{code}/answers", json={"player_id": p[MEENA], "step_id": "s1", "option_id": "b"})
    v = app_h.get(f"/drills/{code}", params={"player_id": host}).json()
    assert v["status"] == "open"                # Ravi hasn't answered, so the step is still open
    app_h.post(f"/drills/{code}/advance", json={"player_id": host})            # close s1 -> review
    v = app_h.get(f"/drills/{code}", params={"player_id": host}).json()
    assert v["status"] == "review" and v["can_advance"] is True
    assert v["review"]["answers"] == [
        {"name": "Meena", "option_text": "Unplug the network cable / turn Wi-Fi off; leave the PC on", "correct": True},
        {"name": "Ravi", "option_text": None, "correct": False}]


def test_result_feeds_the_latest_restore_run(make_app):
    h = make_app()
    h.reset()
    code, p = _start(h)
    host = p[OWNER]
    run = h.post("/restore/run")
    assert run.status_code == 200
    for _ in range(9):                            # lobby -> finished
        h.post(f"/drills/{code}/advance", json={"player_id": host})
    r = h.get(f"/drills/{code}", params={"player_id": host}).json()["results"]
    assert r["restore"] == {"result": "FAIL"}      # the demo faults
