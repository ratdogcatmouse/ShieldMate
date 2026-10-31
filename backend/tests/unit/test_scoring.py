"""Scoring as a pure function (T1.11 / T2.07): per-phase scores and missed action IDs.

Exercised here on a small inline scenario so the logic is tested in isolation, without a
DB. (The full engine-level T1.11 run lives in test_engine.py against the real file.)
"""
from __future__ import annotations

from drills import scoring

SCENARIO = {
    "scenario_id": "x",
    "steps": [
        {"step_id": "s1", "phase": "detect",
         "options": {"staff": [
             {"option_id": "a", "actions": [], "correct": False},
             {"option_id": "b", "actions": ["ISOLATE_NETWORK"], "correct": True}],
             "owner": []}},
        {"step_id": "s2", "phase": "contain",
         "options": {"staff": [
             {"option_id": "a", "actions": [], "correct": False},
             {"option_id": "b", "actions": ["CALL_SAVED_IT", "NOTIFY_OWNER"], "correct": True}],
             "owner": []}},
    ],
}
PLAYERS = [
    {"player_id": 1, "name": "Meena", "role": "front_desk"},
    {"player_id": 2, "name": "Ravi", "role": "billing"},
]


def test_missed_actions_are_the_right_option_actions_deduped_in_order():
    # Meena: both right. Ravi: s1 wrong, s2 wrong.
    answers = [
        {"player_id": 1, "step_id": "s1", "option_id": "b", "correct": True, "action_ids": ["ISOLATE_NETWORK"]},
        {"player_id": 1, "step_id": "s2", "option_id": "b", "correct": True, "action_ids": ["CALL_SAVED_IT", "NOTIFY_OWNER"]},
        {"player_id": 2, "step_id": "s1", "option_id": "a", "correct": False, "action_ids": []},
        {"player_id": 2, "step_id": "s2", "option_id": "a", "correct": False, "action_ids": []},
    ]
    r = scoring.results(SCENARIO, PLAYERS, answers)
    by = {p["name"]: p for p in r["players"]}
    assert by["Meena"]["missed_actions"] == []
    # Ravi missed s1's ISOLATE_NETWORK then s2's CALL_SAVED_IT, NOTIFY_OWNER - step order.
    assert by["Ravi"]["missed_actions"] == ["ISOLATE_NETWORK", "CALL_SAVED_IT", "NOTIFY_OWNER"]
    # per-phase: each player faced detect and contain, one question each.
    assert by["Meena"]["by_phase"] == {"detect": {"correct": 1, "total": 1},
                                       "contain": {"correct": 1, "total": 1}}
    assert by["Ravi"]["by_phase"] == {"detect": {"correct": 0, "total": 1},
                                      "contain": {"correct": 0, "total": 1}}
    assert r["team"] == {"correct": 2, "total": 4}
    assert r["phases"] == ["detect", "contain", "recover", "report"]
    assert r["restore"] is None


def test_an_unanswered_step_counts_as_missed():
    answers = [{"player_id": 2, "step_id": "s1", "option_id": "a", "correct": False, "action_ids": []}]
    r = scoring.results(SCENARIO, PLAYERS, answers)
    by = {p["name"]: p for p in r["players"]}
    # Meena answered nothing -> wrong at s1 and s2 -> misses every correct action.
    assert by["Meena"]["missed_actions"] == ["ISOLATE_NETWORK", "CALL_SAVED_IT", "NOTIFY_OWNER"]
    # Ravi only faced-then-missed s1; s2 has no answer so it also counts wrong.
    assert by["Ravi"]["missed_actions"] == ["ISOLATE_NETWORK", "CALL_SAVED_IT", "NOTIFY_OWNER"]


def test_a_role_with_no_options_at_a_step_scores_nothing_for_it():
    scenario = {"steps": [
        {"step_id": "s1", "phase": "detect",
         "options": {"staff": [], "owner": [
             {"option_id": "a", "actions": [], "correct": False},
             {"option_id": "b", "actions": ["BLOCK_IP"], "correct": True}]}}]}
    players = [{"player_id": 1, "name": "Meena", "role": "front_desk"},
               {"player_id": 2, "name": "Dr. Rao", "role": "owner"}]
    answers = [{"player_id": 2, "step_id": "s1", "option_id": "b", "correct": True, "action_ids": ["BLOCK_IP"]}]
    r = scoring.results(scenario, players, answers)
    by = {p["name"]: p for p in r["players"]}
    # Meena had no staff options -> nothing in by_phase, no missed actions.
    assert by["Meena"]["by_phase"] == {} and by["Meena"]["missed_actions"] == []
    assert by["Dr. Rao"]["by_phase"] == {"detect": {"correct": 1, "total": 1}}
    assert r["team"] == {"correct": 1, "total": 1}


def test_restore_result_is_carried_through():
    answers = []
    r = scoring.results(SCENARIO, PLAYERS, answers, restore_result="FAIL")
    assert r["restore"] == {"result": "FAIL"}
