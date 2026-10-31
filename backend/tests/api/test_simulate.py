"""Attack simulation (T8): the in-app attacker generates Wazuh-shaped alerts from a script.

The simulator is an ``AlertSource`` (like the replay source): ``next_batch`` yields
``RawAlert``s; the pipeline is what turns them into cards. In production the 5 s ingest
loop is that processor; here we drive ``next_batch`` off a ``FakeClock`` (deterministic)
and, where a test wants to see the cards, drain the batch through the pipeline by hand.
"""
from __future__ import annotations

from alerts import pipeline
from alerts.normalise import normalise
from clock import now_iso


def _start(h, script_id):
    r = h.post(f"/demo/simulate/{script_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _advance_to_due(h, ms):
    """Advance the clock by ``ms`` real milliseconds (the FakeClock takes seconds)."""
    h.advance(ms / 1000.0)


def _drain(h) -> int:
    """Run one ingest cycle: push every due sim phase through the pipeline. Returns cards created."""
    created = 0
    for raw in h.ctx.sim.next_batch():
        outcome = pipeline.process(normalise(raw, now_iso(h.clock)), h.ctx.db, h.clock,
                                   lessons=h.ctx.lessons, config=h.ctx.config)
        if outcome == "created":
            created += 1
    return created


# --- the branches (roadmap 1.2) ------------------------------------------------------

def test_contained_branch(make_app):
    h = make_app(simulate=True, actions=True)      # actions on: the storm proposes a BLOCK_IP
    h.reset()
    _start(h, "ransom_wave")                       # multiplier 5: escalations due at 150 s and 300 s
    run = h.ctx.sim
    _drain(h)                                      # t=0 storm fires through the pipeline -> BLOCK_IP proposed
    h.ctx.db.execute("UPDATE actions SET status='executed' WHERE action_id='BLOCK_IP'")
    _advance_to_due(h, 301_000)                   # past both escalations
    assert run.next_batch() == []                 # both cancellable phases skipped
    out = run.run_out()
    assert out["status"] == "contained" and out["phases_cancelled"] == 2
    assert out["phases_fired"] == 1               # only the initial storm actually fired


def test_spread_when_team_does_nothing(make_app):
    h = make_app(simulate=True)
    h.reset()
    _start(h, "ransom_wave")
    run = h.ctx.sim
    _advance_to_due(h, 301_000)                    # all three phases due
    batch = run.next_batch()
    assert [b["alert"]["rule"]["id"] for b in batch] == ["60204", "60106", "100201"]
    assert run.run_out()["status"] == "spread"


def test_spread_alerts_land_in_the_pipeline(make_app):
    h = make_app(simulate=True)
    h.reset()
    _start(h, "ransom_wave")
    _advance_to_due(h, 301_000)
    created = _drain(h)                            # one ingest cycle
    assert created >= 1                            # at least the ransomware card
    owner = h.get("/alerts?role=owner").json()["alerts"]
    assert [a["rule_id"] for a in owner][:1] == ["100201"]  # the encrypt wave's card


def test_stop_ends_the_run(make_app):
    h = make_app(simulate=True)
    h.reset()
    _start(h, "ransom_wave")
    h.ctx.sim.next_batch()
    r = h.post("/demo/simulate/stop")
    assert r.status_code == 200
    assert r.json()["run"]["status"] == "stopped"
    assert h.get("/demo/simulate").json()["run"]["status"] == "stopped"


def test_expired_when_the_window_passes(make_app):
    h = make_app(simulate=True, sim_time_limit_ms=30_000)   # 30 s limit
    h.reset()
    _start(h, "ransom_wave")
    run = h.ctx.sim
    _advance_to_due(h, 40_000)                  # window already gone; the storm still fires
    run.next_batch()
    out = run.run_out()
    assert out["status"] == "expired" and "limit" in out["outcome_reason"]
    assert run.next_batch() == []               # a finished run yields nothing


def test_external_ids_dedupe_repeat_polls(make_app):
    h = make_app(simulate=True)
    h.reset()
    _start(h, "ransom_wave")
    run = h.ctx.sim
    first = run.next_batch()
    assert run.next_batch() == []                   # same tick, nothing new
    _advance_to_due(h, 160_000)
    second = run.next_batch()
    assert len({b["external_id"] for b in first + second}) == len(first) + len(second)


def test_deterministic_run(make_app):
    outcomes = []
    for _ in range(2):
        h = make_app(simulate=True)
        h.reset()
        _start(h, "phish_owner")                    # multiplier 4
        run = h.ctx.sim
        run.next_batch()
        _advance_to_due(h, 45_000)
        out = run.run_out()
        outcomes.append((out["status"], out["phases_fired"], out["phases_cancelled"]))
    assert outcomes[0] == outcomes[1]


# --- default-off and the seam edges --------------------------------------------------

def test_simulation_default_off(make_app):
    h = make_app()                                  # simulate=False
    assert h.ctx.sim is None
    assert h.get("/status").json()["flags"]["SIMULATE"] is False
    assert (h.post("/demo/simulate/ransom_wave").status_code,
            h.get("/demo/simulate").status_code) == (404, 404)
    assert h.inject("password_guessing")["click"] == 1          # the stage fallback still works


def test_unknown_script_is_invalid(make_app):
    h = make_app(simulate=True)
    h.reset()
    r = h.post("/demo/simulate/nope")
    assert (r.status_code, r.json()["error"]) == (400, "invalid_request")


def test_second_start_refused_while_running(make_app):
    h = make_app(simulate=True)
    h.reset()
    _start(h, "ransom_wave")
    assert h.post("/demo/simulate/phish_owner").status_code == 409
    h.post("/demo/simulate/stop")
    assert h.post("/demo/simulate/phish_owner").status_code == 200
