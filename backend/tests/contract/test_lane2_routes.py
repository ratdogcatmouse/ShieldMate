"""T0.02 for the Lane 2 routes: a live response for each validates against contract.py.

(Lane 1's routes are covered by tests/contract/test_routes.py; that module's
fixture-vs-model checks already cover all 21 routes, so here I only prove the live
responses for the drill, restore and device routes.)"""
import pytest

from contract import ROUTES

L2 = [r for r in ROUTES if r.path.startswith(("/drills", "/restore/", "/devices"))]


@pytest.mark.parametrize("route", L2, ids=lambda r: f"{r.method} {r.path}")
def test_lane2_response_validates(make_app, route):
    h = make_app(actions=True)
    h.reset()
    # A drill exists so the view/answer routes have something to render, and a
    # restore run exists so GET /restore/latest reads back a stored row.
    created = h.post("/drills", json={"scenario_id": "ransomware_clinic",
                                       "host_staff_id": 3, "source_alert_id": None})
    assert created.status_code == 200, created.text
    code, host_pid = created.json()["code"], created.json()["player_id"]
    # Meena joins and the step is open, so a staff player can answer and the
    # review panel has a second entry.
    assert h.post("/drills/%s/join" % code, json={"staff_id": 1}).status_code == 200
    meena_pid = h.post("/drills/%s/join" % code, json={"staff_id": 1}).json()["player_id"]
    assert h.post("/drills/%s/advance" % code, json={"player_id": host_pid}).status_code == 200
    assert h.post("/restore/run").status_code == 200

    def fill(path: str) -> str:
        return path.replace("{code}", code)

    query = {f"GET {route.path}": f"?player_id={host_pid}"}.get(f"{route.method} {route.path}", "")
    body = None
    if route.request is not None:
        values = {"scenario_id": "ransomware_clinic", "host_staff_id": 3, "source_alert_id": None,
                  "staff_id": 1, "player_id": host_pid, "step_id": "s1", "option_id": "b"}
        if route.path == "/drills/{code}/answers":
            # The host has no s1 options; a staff player's answer is the 200 case.
            values["player_id"] = meena_pid
        body = {k: values[k] for k in route.request.model_fields}
    path = fill(route.path) + query
    resp = h.client.request(route.method, "/api" + path, json=body)
    assert resp.status_code == 200, f"{route.method} {route.path} -> {resp.status_code}: {resp.text}"
    route.response.model_validate(resp.json())
