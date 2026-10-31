"""POST /events: the phones' UI events. The fixture itself is checked by test_routes.py's ROUTES loop."""
import pytest

from contract import EventsAccepted

MEENA = 1


def ev(type_="ui.page_view", **over):
    return {"type": type_, "client_ts": "2026-11-01T04:00:01.250Z", "path": "/staff/1", "staff_id": MEENA,
            "data": {}} | over


def test_a_batch_is_stored_as_client_events(app_h):
    batch = [ev(), ev("ui.lang_changed", data={"lang": "kn", "from_lang": "en", "evil": "x"}),
             ev("ui.app_error", staff_id=None, data={"message": "x" * 500})]
    r = app_h.post("/events", json={"session_id": "tab-1", "events": batch})
    assert r.status_code == 200
    assert EventsAccepted.model_validate(r.json()).accepted == 3

    stored = app_h.events("ui.")
    assert [e["origin"] for e in stored] == ["client"] * 3
    assert {e["session_id"] for e in stored} == {"tab-1"}
    assert (stored[0]["actor_staff_id"], stored[0]["actor_role"]) == (MEENA, "front_desk")
    assert stored[0]["ts"] == "2026-11-01T04:00:00Z"                          # server time, not the phone's
    assert stored[0]["data"] == {"path": "/staff/1", "client_ts": "2026-11-01T04:00:01.250Z"}
    assert stored[1]["data"] == {"lang": "kn", "from_lang": "en", "path": "/staff/1",
                                 "client_ts": "2026-11-01T04:00:01.250Z"}     # "evil" dropped
    assert len(stored[2]["data"]["message"]) == 200 and stored[2]["actor_staff_id"] is None
    assert app_h.events("request.completed") == []                            # not logged twice


@pytest.mark.parametrize("body", [
    {"session_id": "tab-1", "events": [ev("ui.nope")]},                       # not a client event type
    {"session_id": "tab-1", "events": [ev("alert.done")]},                    # server types can't be forged
    {"session_id": "tab-1", "events": [ev()] * 51},                           # batch too big
    {"session_id": "tab-1", "events": [ev() | {"extra": 1}]},                 # unknown field
    {"session_id": "tab-1", "events": [ev(data={"nested": {"a": 1}})]},       # data values are flat
    {"session_id": "not a session!", "events": [ev()]},
], ids=["type", "server_type", "too_many", "extra_field", "nested_data", "session_id"])
def test_bad_batches_are_invalid_request(app_h, body):
    r = app_h.post("/events", json=body)
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")
    assert app_h.events("ui.") == []
