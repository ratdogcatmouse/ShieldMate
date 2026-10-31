"""T0.02: every fixture is a valid body of its model, and every Lane 1 route's live response
validates against contract.py. (Lane 2 routes are checked by their owner's contract tests.)"""
import json
from pathlib import Path

import pytest

from contract import EXTRA_FIXTURES, ROUTES

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
LANE_ONE = ("/clinic", "/status", "/alerts", "/notifications", "/actions", "/demo")


@pytest.mark.parametrize("route", ROUTES, ids=lambda r: f"{r.method} {r.path}")
def test_fixture_matches_model(route):
    route.response.model_validate(json.loads((FIXTURES / route.fixture).read_text()))


@pytest.mark.parametrize("name,model", EXTRA_FIXTURES.items())
def test_extra_fixtures(name, model):
    model.model_validate(json.loads((FIXTURES / name).read_text()))


def lane_one(route) -> bool:
    return route.path.startswith(LANE_ONE)


def fill_path(path: str, **ids) -> str:
    return path.replace("{id}", str(ids["id"])).replace("{alert_type}", "password_guessing")


@pytest.mark.parametrize("route", [r for r in ROUTES if lane_one(r)], ids=lambda r: f"{r.method} {r.path}")
def test_live_response_validates_against_contract(make_app, route):
    # Undo is off by default (decision 9); turn it on just to see the undone body's shape.
    h = make_app(actions=True, ai_reword=True, undo_supported=route.path.endswith("/undo"))
    h.reset()
    h.inject("password_guessing")                              # alert 2, action 1
    if route.path.endswith("/undo"):
        assert h.post("/actions/1/approve", json={"staff_id": 3}).status_code == 200
    values = {"staff_id": 3, "enabled": True, "role": "owner", "lang": "en"}
    body = {k: values[k] for k in route.request.model_fields} if route.request else None
    path = fill_path(route.path, id=1 if "actions" in route.path else 2)
    query = {"/alerts": "?role=front_desk", "/notifications": "?role=owner"}.get(route.path, "")
    resp = h.client.request(route.method, "/api" + path + query, json=body)
    assert resp.status_code == 200, resp.text
    route.response.model_validate(resp.json())
    assert resp.json().keys() == json.loads((FIXTURES / route.fixture).read_text()).keys()


def test_refused_action_matches_its_fixture(make_app):
    h = make_app(actions=True)
    h.reset()
    h.inject("password_guessing")
    h.ctx.db.execute("UPDATE actions SET status='refused', target_ip='192.168.1.1', refused_reason='192.168.1.1 is the clinic router'")
    got = h.get("/actions").json()["actions"][0]
    want = json.loads((FIXTURES / "action_refused.json").read_text())
    assert {k: got[k] for k in want if k not in ("id", "alert_id")} == {k: v for k, v in want.items() if k not in ("id", "alert_id")} | {"proposed_at": got["proposed_at"]}


def test_replay_response_matches_fixture(make_app):
    h = make_app()
    h.reset()
    assert h.post("/demo/replay/password_guessing").json() == json.loads((FIXTURES / "demo_replay.json").read_text())
