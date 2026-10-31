"""v4 over HTTP: the three new drills (learning mode) and their attack scripts (test mode).

Learning mode: a role-specific option list reaches only that role's phone, and answering
another role's option is refused. Test mode: the cards reach the right phones, ticking the
script's ``contain_on`` step on a card stops the later phases, the result (and who stopped
it) is on GET /status, and the three original scripts still ignore card ticks.
"""
from __future__ import annotations

from alerts import pipeline
from alerts.normalise import normalise
from clock import now_iso

OWNER, MEENA, RAVI = 3, 1, 2


# --- helpers ---------------------------------------------------------------------

def _drill(h, scenario_id):
    r = h.post("/drills", json={"scenario_id": scenario_id, "host_staff_id": OWNER, "source_alert_id": None})
    assert r.status_code == 200, r.text
    code, players = r.json()["code"], {OWNER: r.json()["player_id"]}
    for staff in (MEENA, RAVI):
        players[staff] = h.post(f"/drills/{code}/join", json={"staff_id": staff}).json()["player_id"]
    return code, players


def _view(h, code, pid):
    return h.get(f"/drills/{code}", params={"player_id": pid}).json()


def _sim(h, script_id):
    r = h.post(f"/demo/simulate/{script_id}")
    assert r.status_code == 200, r.text
    return h.ctx.sim


def _drain(h) -> list[str]:
    """One ingest cycle; returns the rule IDs of the cards it created."""
    made = []
    for raw in h.ctx.sim.next_batch():
        alert = normalise(raw, now_iso(h.clock))
        if pipeline.process(alert, h.ctx.db, h.clock, lessons=h.ctx.lessons, config=h.ctx.config) == "created":
            made.append(alert.rule_id)
    return made


def _card(h, role, rule_id):
    return next(a for a in h.get("/alerts", params={"role": role}).json()["alerts"] if a["rule_id"] == rule_id)


def _tick(h, alert_id, action, staff, done=True):
    r = h.put(f"/alerts/{alert_id}/steps/{action}", json={"staff_id": staff, "done": done})
    assert r.status_code == 200, r.text


# --- learning mode ------------------------------------------------------------------

def test_ravi_and_meena_see_different_choices(app_h):
    app_h.reset()
    code, p = _drill(app_h, "supplier_bank_fraud")
    app_h.post(f"/drills/{code}/advance", json={"player_id": p[OWNER]})          # lobby -> s1
    ravi, meena = _view(app_h, code, p[RAVI]), _view(app_h, code, p[MEENA])
    assert len(ravi["options"]) == 3 and ravi["waiting_message"] is None
    assert meena["options"] == [] and meena["waiting_message"]                   # Meena waits this one out
    assert ravi["team"]["total"] == 1                                            # only Ravi has to answer
    # Meena can't answer with Ravi's options; Ravi's right answer carries the new action ID.
    bad = app_h.post(f"/drills/{code}/answers", json={"player_id": p[MEENA], "step_id": "s1", "option_id": "b"})
    assert bad.json()["error"] == "invalid_option"
    ok = app_h.post(f"/drills/{code}/answers", json={"player_id": p[RAVI], "step_id": "s1", "option_id": "b"}).json()
    assert ok["correct"] is True and ok["actions"] == ["VERIFY_BY_CALLBACK"]


def test_new_drills_run_to_a_finished_result(app_h):
    for scenario_id in ("phish_doctor_email", "tech_support_call", "supplier_bank_fraud"):
        app_h.reset()
        code, p = _drill(app_h, scenario_id)
        for _ in range(9):                         # lobby, then open + review for each of the 4 steps
            app_h.post(f"/drills/{code}/advance", json={"player_id": p[OWNER]})
        v = _view(app_h, code, p[RAVI])
        assert v["status"] == "finished", scenario_id
        rows = {r["name"]: r for r in v["results"]["players"]}
        assert set(rows) == {"Meena", "Ravi"}      # the host isn't scored
        assert rows["Ravi"]["missed_actions"]      # nobody answered: every right answer is listed


# --- test mode: the attack scripts --------------------------------------------------

def test_meena_unplugging_stops_the_tech_support_attack(make_app):
    h = make_app(simulate=True)
    h.reset()
    run = _sim(h, "tech_support_call")
    assert _drain(h) == ["100320"]
    card = _card(h, "front_desk", "100320")
    assert "ISOLATE_NETWORK" in [s["action"] for s in card["card"]["steps"]]
    h.advance(30)
    _tick(h, card["id"], "ISOLATE_NETWORK", MEENA)
    h.advance(200)                                 # past both later phases
    assert _drain(h) == []                         # remote session and file copy never happen
    out = run.run_out()
    assert (out["status"], out["phases_fired"], out["phases_cancelled"]) == ("contained", 1, 2)
    sim = h.get("/status").json()["simulation"]
    assert sim["status"] == "contained" and sim["stop_actions"] == ["ISOLATE_NETWORK"]
    assert sim["contained_by"]["action"] == "ISOLATE_NETWORK" and sim["contained_by"]["staff_id"] == MEENA
    assert sim["title"].startswith("A fake")


def test_tech_support_attack_spreads_when_nobody_acts(make_app):
    h = make_app(simulate=True)
    h.reset()
    run = _sim(h, "tech_support_call")
    _drain(h)
    h.advance(200)
    assert _drain(h) == ["100321", "100322"]
    assert run.run_out()["status"] == "spread"
    sim = h.get("/status").json()["simulation"]
    assert sim["contained_by"] is None and sim["stop_actions"] == ["ISOLATE_NETWORK"]
    owner_rules = [a["rule_id"] for a in h.get("/alerts", params={"role": "owner"}).json()["alerts"]]
    assert {"100320", "100321", "100322"} <= set(owner_rules)


def test_the_wrong_step_does_not_contain(make_app):
    h = make_app(simulate=True)
    h.reset()
    run = _sim(h, "tech_support_call")
    _drain(h)
    _tick(h, _card(h, "front_desk", "100320")["id"], "NOTIFY_OWNER", MEENA)
    h.advance(200)
    _drain(h)
    assert run.run_out()["status"] == "spread"


def test_a_tick_taken_back_still_counts(make_app):
    """The team did act in time; the latch keeps that even if the box is unticked later."""
    h = make_app(simulate=True)
    h.reset()
    run = _sim(h, "tech_support_call")
    _drain(h)
    card = _card(h, "front_desk", "100320")
    _tick(h, card["id"], "ISOLATE_NETWORK", MEENA)
    h.advance(5)
    _drain(h)                                      # the poll that latches it
    _tick(h, card["id"], "ISOLATE_NETWORK", MEENA, done=False)
    h.advance(200)
    _drain(h)
    assert run.run_out()["status"] == "contained"


def test_ravi_checking_by_phone_stops_the_supplier_payment(make_app):
    h = make_app(simulate=True)
    h.reset()
    run = _sim(h, "supplier_bank_fraud")
    assert _drain(h) == ["100330"]
    # Ravi is told (it fires on FILE-SERVER, his computer), Meena isn't; his card shows the lookalike sender.
    notes = h.get("/notifications", params={"role": "billing"}).json()["notifications"]
    assert any(n["kind"] == "attack" for n in notes)
    assert not h.get("/notifications", params={"role": "front_desk"}).json()["notifications"]
    card = _card(h, "billing", "100330")
    assert card["card"]["log_fields"] == {"sender": "accounts@shreelab-supplies.in"}
    assert card["card"]["drill_scenario"] == "supplier_bank_fraud"
    _tick(h, card["id"], "VERIFY_BY_CALLBACK", RAVI)
    h.advance(130)
    assert _drain(h) == []                          # the payment never goes out
    assert run.run_out()["status"] == "contained"
    assert h.get("/status").json()["simulation"]["contained_by"]["staff_id"] == RAVI


def test_payment_card_is_critical_when_the_attack_spreads(make_app):
    h = make_app(simulate=True)
    h.reset()
    _sim(h, "supplier_bank_fraud")
    _drain(h)
    h.advance(130)
    assert _drain(h) == ["100331"]
    pay = _card(h, "billing", "100331")
    assert pay["impact"]["level"] == "critical"
    assert [s["action"] for s in pay["card"]["steps"]][:2] == ["STOP_PAYMENT", "REPORT_1930"]
    assert h.get("/actions").status_code == 404 or h.get("/actions").json()["actions"] == []


def test_doctor_changing_the_password_stops_the_mail_out(make_app):
    h = make_app(simulate=True)
    h.reset()
    run = _sim(h, "phish_doctor_email")
    assert _drain(h) == ["61320"]
    assert _card(h, "owner", "61320")["card"]["log_fields"] == {"sender": "accounts@clinc-payments.in"}
    h.advance(61)
    assert _drain(h) == ["100310"]                  # the sign-in from outside always happens (the click came first)
    _tick(h, _card(h, "owner", "100310")["id"], "CHANGE_PASSWORD", OWNER)
    h.advance(130)
    assert _drain(h) == []
    out = run.run_out()
    assert (out["status"], out["phases_fired"], out["phases_cancelled"]) == ("contained", 2, 1)


def test_a_correct_drill_answer_also_contains(make_app):
    h = make_app(simulate=True)
    h.reset()
    run = _sim(h, "supplier_bank_fraud")
    _drain(h)
    code, p = _drill(h, "supplier_bank_fraud")
    h.post(f"/drills/{code}/advance", json={"player_id": p[OWNER]})
    h.post(f"/drills/{code}/answers", json={"player_id": p[RAVI], "step_id": "s1", "option_id": "b"})
    h.advance(130)
    _drain(h)
    assert run.run_out()["status"] == "contained"


def test_original_scripts_still_ignore_card_ticks(make_app):
    """Decision 4 (B): ransom_wave and friends keep the original check exactly."""
    h = make_app(simulate=True)
    h.reset()
    run = _sim(h, "ransom_wave")
    _drain(h)
    alert_id = h.ctx.db.one("SELECT id FROM alerts WHERE external_id LIKE 'sim:%'")["id"]
    h.ctx.db.execute("INSERT INTO alert_steps (alert_id, action, done_by, done_at) VALUES (?, 'ISOLATE_NETWORK', 1, ?)",
                     (alert_id, now_iso(h.clock)))
    h.advance(301)
    _drain(h)
    assert run.run_out()["status"] == "spread"
    sim = h.get("/status").json()["simulation"]
    assert sim["stop_actions"] == ["BLOCK_IP", "ISOLATE_NETWORK"] and sim["contained_by"] is None


def test_status_simulation_is_null_when_off_or_reset(make_app):
    assert make_app().get("/status").json()["simulation"] is None              # flag off
    h = make_app(simulate=True)
    h.reset()
    assert h.get("/status").json()["simulation"] is None                       # nothing run yet
    _sim(h, "supplier_bank_fraud")
    assert h.get("/status").json()["simulation"]["status"] == "running"
    h.reset()
    assert h.get("/status").json()["simulation"] is None                       # Reset clears it


def test_bad_contain_on_is_refused(make_app, tmp_path):
    import json
    (tmp_path / "bad.json").write_text(json.dumps({
        "id": "bad", "contain_on": ["PRESS_THE_RED_BUTTON"],
        "phases": [{"at_ms": 0, "alert": {"rule": {"id": "1", "level": 9}, "agent": {"name": "X"}}}]}))
    h = make_app(simulate=True, sim_dir=tmp_path)
    h.reset()
    r = h.post("/demo/simulate/bad")
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")
