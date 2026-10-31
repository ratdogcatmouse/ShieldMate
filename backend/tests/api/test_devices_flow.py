"""API tests for the device strip: T4.10 (the status walks ok -> under_attack ->
protected -> ok through the alert and action story) and the block object."""

OWNER = 3


def _by_agent(body):
    return {d["agent_name"]: d for d in body["devices"]}


def test_t4_10_strip_follows_the_story(make_app):
    h = make_app(actions=True)
    h.reset()
    h.inject("password_guessing")

    # A new 60204 alert flips that PC to under_attack; the others stay ok (T4.10).
    by = _by_agent(h.get("/devices").json())
    assert by["RECEPTION-PC"]["status"] == "under_attack"
    assert by["RECEPTION-PC"]["status_changed_at"] is not None
    assert by["RECEPTION-PC"]["block"] is None                 # no block executed yet
    assert by["FILE-SERVER"]["status"] == "ok" and by["FILE-SERVER"]["status_changed_at"] is None

    # Approving the simulated block protects the PC and attaches the block object.
    aid = h.get("/actions?status=proposed").json()["actions"][0]["id"]
    h.post(f"/actions/{aid}/approve", json={"staff_id": OWNER})
    by = _by_agent(h.get("/devices").json())
    assert by["RECEPTION-PC"]["status"] == "protected"
    assert by["RECEPTION-PC"]["block"] == {
        "action_row_id": aid, "target_ip": "192.168.1.57", "expires_at": "2026-11-01T05:00:00Z"}

    # An hour later the block expires: back to ok, block cleared, timestamp kept.
    h.advance(3600)
    h.tick()
    by = _by_agent(h.get("/devices").json())
    assert by["RECEPTION-PC"]["status"] == "ok" and by["RECEPTION-PC"]["block"] is None
    assert by["RECEPTION-PC"]["status_changed_at"] == "2026-11-01T05:00:00Z"


def test_done_while_blocked_keeps_protected_then_expiry_returns_ok(make_app):
    h = make_app(actions=True)
    h.reset()
    h.inject("password_guessing")
    aid = h.get("/actions?status=proposed").json()["actions"][0]["id"]
    h.post(f"/actions/{aid}/approve", json={"staff_id": OWNER})
    alert_id = h.get("/alerts?role=owner").json()["alerts"][0]["id"]
    # T4.10: "done" with an active block in place does NOT unset the strip.
    h.post(f"/alerts/{alert_id}/done", json={"staff_id": 1})
    by = _by_agent(h.get("/devices").json())
    assert by["RECEPTION-PC"]["status"] == "protected"
    h.advance(3600)
    h.tick()
    assert _by_agent(h.get("/devices").json())["RECEPTION-PC"]["status"] == "ok"


def test_devices_flag_off_404s(app_h):
    r = app_h.get("/devices")
    assert (r.status_code, r.json()["error"]) == (404, "not_enabled")
