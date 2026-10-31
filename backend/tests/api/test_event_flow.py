"""API tests for the event log: each story leaves the right trail, and no free text gets in."""
import json
import sqlite3

from alerts import pipeline
from drills.engine import registry

OWNER, MEENA, RAVI = 3, 1, 2


def types(events) -> list[str]:
    return [e["type"] for e in events]


def one(h, type_):
    [ev] = h.events(type_)
    return ev


# --- alerts ----------------------------------------------------------------------

def test_alert_story_is_logged_in_order_with_its_request(app_h):
    app_h.reset()
    app_h.inject("password_guessing")
    app_h.post("/alerts/2/done", json={"staff_id": MEENA}, headers={"X-Session-Id": "tab-1"})

    trail = [t for t in types(app_h.events()) if t != "request.completed"]
    assert trail == ["system.started", "demo.reset", "alert.filtered", "alert.created",
                     "device.status_changed", "demo.replay", "alert.done", "notification.sent",
                     "device.status_changed"]
    done = one(app_h, "alert.done")
    assert (done["actor_staff_id"], done["actor_role"], done["session_id"]) == (MEENA, "front_desk", "tab-1")
    assert done["data"] == {"rule_id": "60204", "lang": "en", "already_done": False}
    assert one(app_h, "alert.filtered")["data"]["reason"] == "no_lesson"

    # The request that caused it carries the same request id, and only the route's template.
    req = next(e for e in app_h.events("request.completed") if e["request_id"] == done["request_id"])
    assert req["data"]["route"] == "/alerts/{alert_id}/done" and req["data"]["status"] == 200
    assert req["session_id"] == "tab-1"


def test_a_repeat_done_tap_is_logged_but_sends_nothing(app_h):
    app_h.reset(); app_h.inject("password_guessing")
    app_h.post("/alerts/2/done", json={"staff_id": MEENA})
    app_h.post("/alerts/2/done", json={"staff_id": MEENA})
    assert [e["data"]["already_done"] for e in app_h.events("alert.done")] == [False, True]
    assert len(app_h.events("notification.sent")) == 1


def test_each_reset_starts_a_new_epoch(app_h):
    app_h.reset(); app_h.inject("password_guessing")
    app_h.reset(); app_h.inject("password_guessing")
    assert [e["data"]["epoch"] for e in app_h.events("demo.reset")] == [1, 2]
    created = app_h.events("alert.created")
    # Same alert id both times; the epoch is what tells them apart.
    assert [(e["epoch"], e["subject_id"]) for e in created] == [(1, "2"), (2, "2")]


# --- actions ---------------------------------------------------------------------

def test_approval_and_expiry_are_logged(actions_h):
    h = actions_h
    h.reset(); h.inject("password_guessing")
    assert one(h, "action.proposed")["data"] == {"alert_id": 2, "agent_name": "RECEPTION-PC", "simulated": True}
    h.post("/actions/1/approve", json={"staff_id": OWNER})
    ex = one(h, "action.executed")
    assert (ex["actor_staff_id"], ex["actor_role"]) == (OWNER, "owner")
    assert ex["data"]["via"] == "tap" and ex["data"]["expires_at"] == "2026-11-01T05:00:00Z"

    h.advance(3601); h.tick()
    expired = one(h, "action.expired")
    assert expired["actor_staff_id"] is None and expired["request_id"] is None     # the background pass
    moves = [(e["data"]["from_status"], e["data"]["to_status"]) for e in h.events("device.status_changed")]
    assert moves == [("ok", "under_attack"), ("under_attack", "protected"), ("protected", "ok")]


def test_an_unanswered_proposal_escalates(actions_h):
    h = actions_h
    h.reset(); h.inject("password_guessing")
    h.advance(301); h.tick()
    esc = one(h, "action.escalated")
    assert esc["actor_staff_id"] is None
    assert esc["data"] == {"alert_id": 2, "to_staff_id": RAVI, "waited_s": 301}


def test_decline_and_standing_rule_are_logged(actions_h):
    h = actions_h
    h.reset(); h.inject("password_guessing")
    h.post("/actions/1/decline", json={"staff_id": OWNER})
    h.put("/clinic/standing-rule", json={"enabled": True, "staff_id": OWNER})
    assert one(h, "action.declined")["actor_staff_id"] == OWNER
    assert one(h, "clinic.standing_rule_set")["data"] == {"enabled": True}


def test_a_refused_block_logs_a_code_not_the_reason_text(actions_h):
    h = actions_h
    h.reset(); h.inject("password_guessing")
    ip = h.ctx.db.one("SELECT target_ip FROM actions WHERE id = 1")["target_ip"]
    h.ctx.db.execute("UPDATE clinic SET never_block = ?",
                     (json.dumps([{"ip": ip, "label": "the lab printer"}]),))
    assert h.post("/actions/1/approve", json={"staff_id": OWNER}).json()["error"] == "target_refused"
    refused = one(h, "action.refused")
    assert refused["data"] == {"alert_id": 2, "stage": "execute", "reason": "never_block"}
    assert ip not in json.dumps(h.events()) and "printer" not in json.dumps(h.events())


# --- drills and restore ----------------------------------------------------------

def test_drill_story_records_who_answered_and_how_fast(app_h):
    app_h.reset()
    code = app_h.post("/drills", json={"scenario_id": "ransomware_clinic", "host_staff_id": OWNER,
                                        "source_alert_id": None}).json()["code"]
    host = one(app_h, "drill.created")["data"]["player_id"]
    meena = app_h.post(f"/drills/{code}/join", json={"staff_id": MEENA}).json()["player_id"]
    app_h.post(f"/drills/{code}/join", json={"staff_id": MEENA})                  # a reload
    app_h.post(f"/drills/{code}/advance", json={"player_id": host})              # lobby -> open s1
    app_h.advance(12)
    step = registry().get("ransomware_clinic")["steps"][0]
    right = next(o["option_id"] for o in step["options"]["staff"] if o.get("correct"))
    app_h.post(f"/drills/{code}/answers", json={"player_id": meena, "step_id": step["step_id"], "option_id": right})

    assert [e["data"]["rejoin"] for e in app_h.events("drill.joined")] == [False, True]
    ans = one(app_h, "drill.answered")
    assert (ans["actor_staff_id"], ans["subject_id"]) == (MEENA, code)
    assert ans["data"] == {"player_id": meena, "step_id": step["step_id"], "option_id": right,
                           "correct": True, "latency_ms": 12000}
    # Meena was the only one with options, so the step closed itself.
    moves = [(e["data"]["from_status"], e["data"]["to_status"], e["data"]["auto"])
             for e in app_h.events("drill.advanced")]
    assert moves == [("lobby", "open", False), ("open", "review", True)]


def test_restore_check_is_logged_with_counts_only(app_h):
    app_h.reset()
    app_h.post("/restore/run")
    run = one(app_h, "restore.run")
    assert run["data"]["result"] == "FAIL" and run["data"]["files_total"] == 50
    assert set(run["data"]["failed_checks"]) == {"freshness", "integrity", "exposure"}


# --- requests and errors ---------------------------------------------------------

def test_errors_are_logged_with_their_code(app_h):
    app_h.reset()
    app_h.post("/alerts/999/done", json={"staff_id": MEENA})
    app_h.post("/alerts/2/done", json={"nope": 1})
    got = [(e["data"]["status"], e["data"]["error"]) for e in app_h.events("request.completed")][-2:]
    assert got == [(404, "not_found"), (400, "invalid_request")]


def test_a_crash_is_logged_as_error_unhandled(app_h, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(pipeline, "list_alerts", boom)
    assert app_h.get("/alerts?role=owner").status_code == 500
    crash = one(app_h, "error.unhandled")
    assert crash["data"] == {"method": "GET", "route": "/alerts", "exc_type": "RuntimeError"}
    req = app_h.events("request.completed")[-1]
    assert (req["data"]["status"], req["data"]["error"], req["request_id"]) == (500, "internal_error", crash["request_id"])


def test_successful_polls_are_skipped_unless_asked_for(make_app):
    quiet = make_app()
    quiet.get("/alerts?role=owner")
    assert quiet.events("request.completed") == []
    loud = make_app(event_log_reads=True)
    loud.get("/alerts?role=owner")
    assert [e["data"]["method"] for e in loud.events("request.completed")] == ["GET"]


def test_a_bad_session_header_is_ignored(app_h):
    app_h.reset()
    app_h.post("/alerts/999/done", json={"staff_id": MEENA}, headers={"X-Session-Id": "<script>" * 20})
    assert app_h.events("request.completed")[-1]["session_id"] is None


def test_event_log_off_writes_nothing(make_app):
    h = make_app(event_log=False)
    h.reset(); h.inject("password_guessing")
    assert not h.config.events_path.exists()
    r = h.post("/events", json={"session_id": "tab-1", "events": []})
    assert (r.status_code, r.json()["error"]) == (404, "not_enabled")


# --- privacy ---------------------------------------------------------------------

def test_no_log_text_names_or_secrets_reach_the_log(make_app):
    h = make_app(actions=True, ai_reword=True, owner_pin="4321", backstage_token="stage-tok",
                 wazuh_api_password="wazuh-secret")
    owner, stage = {"X-Owner-Pin": "4321"}, {"X-Backstage-Token": "stage-tok"}
    h.client.post("/api/demo/reset", headers=stage)
    for alert_type in h.ctx.replay.types:                 # every replay click, prompt injection included
        while h.ctx.replay.clicks_left(alert_type):
            assert h.client.post(f"/api/demo/replay/{alert_type}", headers=stage).status_code == 200
    h.post("/alerts/2/done", json={"staff_id": MEENA})
    h.post("/alerts/2/reword", json={"role": "owner", "lang": "en"})
    h.post("/actions/1/approve", json={"staff_id": OWNER}, headers=owner)

    conn = sqlite3.connect(h.config.events_path)
    dump = json.dumps(conn.execute("SELECT * FROM events").fetchall())
    conn.close()
    log_text = [v for r in h.ctx.db.query("SELECT log_fields FROM alerts")
                for v in json.loads(r["log_fields"]).values() if isinstance(v, str)]
    notes = [r["text"] for r in h.ctx.db.query("SELECT text FROM notifications")]
    assert log_text and notes
    forbidden = log_text + notes + [s["name"] for s in h.ctx.db.staff_list()] + ["4321", "stage-tok", "wazuh-secret"]
    leaked = [s for s in forbidden if s in dump]
    # Agent names are device names the clinic chose (and the subject of device events), not log text.
    assert [s for s in leaked if s not in {r["agent_name"] for r in h.ctx.db.devices()}] == []
    assert set(one(h, "system.started")["data"]) == {"alert_source", "actions", "ai_reword", "ai_provider",
                                                     "undo_supported", "event_log_reads"}
