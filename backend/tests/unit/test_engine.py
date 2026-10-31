"""Drill engine unit tests: the state machine (T1.06), the T1.11 scripted scoring run,
and the role/waiting/view rules (T1.09, T1.10's auto-close, T4.11's no-action rule)."""
from __future__ import annotations

import pytest

from clock import FakeClock
from config import Config
from db import connect
from drills import engine, models

SCENARIO = "ransomware_clinic"
MEENA, RAVI, OWNER = 1, 2, 3


@pytest.fixture
def h(tmp_path):
    db = connect(Config(db_path=tmp_path / "db.sqlite"))
    reg = engine.ScenarioRegistry()
    yield db, FakeClock(), reg
    db.close()


def _start(db, clock, reg, host=OWNER):
    """Host + Meena + Ravi in a fresh lobby drill. Returns the code and {staff_id: player_id}."""
    out = engine.create(db, clock, SCENARIO, host, None, reg)
    engine.join(db, clock, out["code"], MEENA)
    engine.join(db, clock, out["code"], RAVI)
    players = {r["staff_id"]: r["player_id"] for r in db.query(
        "SELECT staff_id, id AS player_id FROM drill_players WHERE drill_code = ?", (out["code"],))}
    return out["code"], players


# --- T1.06: the state machine ------------------------------------------------

def test_lobby_open_review(h):
    db, clock, reg = h
    code, players = _start(db, clock, reg)
    v = engine.view(db, code, players[OWNER], reg)
    assert (v["status"], v["can_advance"], v["step_index"]) == ("lobby", True, -1)
    v = engine.advance(db, clock, code, players[OWNER], reg)
    assert (v["status"], v["step"]["step_id"], v["step_index"]) == ("open", "s1", 0)
    v = engine.advance(db, clock, code, players[OWNER], reg)          # close s1 early -> review
    assert (v["status"], v["step"]["step_id"]) == ("review", "s1")


def test_review_walks_every_step_then_finishes(h):
    db, clock, reg = h
    code, players = _start(db, clock, reg)
    expected = [("open", "s1"), ("review", "s1"), ("open", "s2"), ("review", "s2"),
                ("open", "s3"), ("review", "s3"), ("open", "s4"), ("review", "s4")]
    for status, step in expected:
        v = engine.advance(db, clock, code, players[OWNER], reg)
        assert (v["status"], v["step"]["step_id"]) == (status, step)
    v = engine.advance(db, clock, code, players[OWNER], reg)          # last review -> finished
    assert v["status"] == "finished" and v["results"] is not None and v["step"] is None
    # A finished drill is finished: no more moves.
    try:
        engine.advance(db, clock, code, players[OWNER], reg)
        assert False, "advance on a finished drill should fail"
    except Exception as exc:
        assert getattr(exc, "code", None) == "drill_finished"


def test_only_the_host_advances(h):
    db, clock, reg = h
    code, players = _start(db, clock, reg)
    try:
        engine.advance(db, clock, code, players[MEENA], reg)
        assert False, "non-host advance should fail"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_host"


def test_unknown_scenario_is_invalid_request(h):
    db, clock, reg = h
    try:
        engine.create(db, clock, "nope", OWNER, None, reg)
        assert False, "unknown scenario should fail"
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_request"


# --- T1.10: the step auto-closes when everyone with options has answered ------

def test_step_closes_when_all_options_players_answered(h):
    db, clock, reg = h
    code, players = _start(db, clock, reg)
    engine.advance(db, clock, code, players[OWNER], reg)             # open s1
    engine.answer(db, clock, code, players[MEENA], "s1", "b", reg)   # s1 staff options; Ravi still open
    assert db.one("SELECT status FROM drills WHERE code = ?", (code,))["status"] == "open"
    engine.answer(db, clock, code, players[RAVI], "s1", "a", reg)    # both staff answered -> review
    assert db.one("SELECT status FROM drills WHERE code = ?", (code,))["status"] == "review"


# --- T1.11: the scripted scoring run ----------------------------------------
# Meena all right, Ravi wrong at s1 and s2 (right at s3, s4), the host answers the
# owner options at s3 and s4. Missed action IDs must match the spec's example.

def test_t1_11_scripted_scoring(h):
    db, clock, reg = h
    code, players = _start(db, clock, reg)
    host, meena, ravi = players[OWNER], players[MEENA], players[RAVI]

    # The run: Meena always right, Ravi wrong at s1 and s2 (right at s3, s4), and the host
    # answers the owner options at s3 and s4 (s1, s2 have no owner options, so the step
    # auto-closes as soon as both staff answer - no host move needed there).
    engine.advance(db, clock, code, host, reg)                        # lobby -> open s1
    engine.answer(db, clock, code, meena, "s1", "b", reg)             # correct
    engine.answer(db, clock, code, ravi, "s1", "c", reg)             # wrong -> s1 auto-closes to review
    engine.advance(db, clock, code, host, reg)                        # review s1 -> open s2
    engine.answer(db, clock, code, meena, "s2", "b", reg)             # correct
    engine.answer(db, clock, code, ravi, "s2", "a", reg)              # wrong -> s2 auto-closes to review
    engine.advance(db, clock, code, host, reg)                        # review s2 -> open s3
    engine.answer(db, clock, code, meena, "s3", "a", reg)             # correct
    engine.answer(db, clock, code, ravi, "s3", "a", reg)             # correct
    engine.answer(db, clock, code, host, "s3", "b", reg)              # owner correct -> s3 auto-closes
    engine.advance(db, clock, code, host, reg)                        # review s3 -> open s4
    engine.answer(db, clock, code, meena, "s4", "a", reg)             # correct
    engine.answer(db, clock, code, ravi, "s4", "a", reg)             # correct
    engine.answer(db, clock, code, host, "s4", "b", reg)              # owner correct -> s4 auto-closes
    engine.advance(db, clock, code, host, reg)                        # review s4 -> finished

    r = engine.view(db, code, host, reg)["results"]
    by_name = {p["name"]: p for p in r["players"]}
    # No host row (the host runs the drill, not plays it) - matches the frozen finished view.
    assert by_name["Meena"]["missed_actions"] == []
    # Ravi wrong at s1 (ISOLATE_NETWORK) and s2 (CALL_SAVED_IT, NOTIFY_OWNER); right at s3/s4.
    assert by_name["Ravi"]["missed_actions"] == ["ISOLATE_NETWORK", "CALL_SAVED_IT", "NOTIFY_OWNER"]
    # Team: Meena 4/4, Ravi 2/4, host's answered s3+s4 -> 8 of 10 (the frozen example).
    assert r["team"] == {"correct": 8, "total": 10}
    assert r["restore"] is None


def test_restored_run_feeds_the_result(h):
    db, clock, reg = h
    code, players = _start(db, clock, reg)
    host = players[OWNER]
    db.execute("INSERT INTO restore_runs (started_at,result,backup_age_hours,files_total,files_ok,exposed,details)"
               " VALUES ('t','FAIL',216.0,50,48,1,'[]')")
    for _ in range(9):          # lobby -> open/review x4 -> finished
        engine.advance(db, clock, code, host, reg)
    assert engine.view(db, code, host, reg)["results"]["restore"] == {"result": "FAIL"}


# --- T1.09 / view rules -----------------------------------------------------

def test_role_options_waiting_and_no_peeking(h):
    db, clock, reg = h
    code, players = _start(db, clock, reg)
    engine.advance(db, clock, code, players[OWNER], reg)             # open s1
    owner_v = engine.view(db, code, players[OWNER], reg)
    # Owner has no s1 options -> waiting message, empty options; as host they can advance.
    assert owner_v["waiting_message"] == "Waiting for the team to decide" and owner_v["options"] == []
    assert owner_v["can_advance"] is True and owner_v["status"] == "open"
    meena = engine.view(db, code, players[MEENA], reg)
    assert [o["option_id"] for o in meena["options"]] == ["a", "b", "c"]
    # The answer key is not leaked before Meena answers.
    assert all("correct" not in o for o in meena["options"]) and meena["my_answer"] is None
    # total counts only the options-havers (staff, not the optionless owner).
    assert meena["team"]["total"] == 2
    assert meena["can_advance"] is False


def test_my_answer_shows_feedback_once_answered(h):
    db, clock, reg = h
    code, players = _start(db, clock, reg)
    engine.advance(db, clock, code, players[OWNER], reg)
    engine.answer(db, clock, code, players[MEENA], "s1", "b", reg)
    meena = engine.view(db, code, players[MEENA], reg)
    assert meena["my_answer"] == {"option_id": "b", "correct": True,
                                   "feedback": "Right. Cutting the network stops the spread and keeps the evidence.",
                                   "actions": ["ISOLATE_NETWORK"]}


def test_review_panel_lists_who_chose_what(h):
    db, clock, reg = h
    code, players = _start(db, clock, reg)
    engine.advance(db, clock, code, players[OWNER], reg)             # open s1
    engine.answer(db, clock, code, players[MEENA], "s1", "b", reg)
    engine.advance(db, clock, code, players[OWNER], reg)             # close s1 -> review
    v = engine.view(db, code, players[OWNER], reg)
    # Ravi never answered s1, so his entry is a null option_text and not correct.
    assert v["review"]["answers"] == [
        {"name": "Meena", "option_text": "Unplug the network cable / turn Wi-Fi off; leave the PC on", "correct": True},
        {"name": "Ravi", "option_text": None, "correct": False}]


def test_t4_11_block_ip_drill_option_creates_no_action(h):
    db, clock, reg = h
    # The only scenario whose owner options name BLOCK_IP is password_guessing (s2).
    out = engine.create(db, clock, "password_guessing", OWNER, None, reg)
    code = out["code"]
    host = out["player_id"]
    engine.advance(db, clock, code, host, reg)                        # open s1
    engine.advance(db, clock, code, host, reg)                        # review s1
    engine.advance(db, clock, code, host, reg)                        # open s2 (owner has a BLOCK_IP option)
    engine.answer(db, clock, code, host, "s2", "a", reg)              # the BLOCK_IP option
    assert db.one("SELECT count(*) AS n FROM actions")["n"] == 0      # drill practice never proposes


def test_models_validate_the_shipped_scenarios():
    for sid, data in engine.registry()._by_id.items():
        models.validate_scenario(data)
