"""End-of-drill results: one point per correct answer, grouped by phase (T1.11, T2.07).

Pure functions on (scenario, players, answers) so they are unit-testable without a DB.
A "missed action" is an action the correct option carried on a step the player got
wrong or never answered - that list is what "you skipped X" would say.
"""
from __future__ import annotations

from typing import get_args

from contract import Phase

PHASES = list(get_args(Phase))           # ["detect", "contain", "recover", "report"]


def _role_key(role: str) -> str:
    """front_desk/billing answer the scenario's "staff" options; owner the "owner" ones."""
    return "owner" if role == "owner" else "staff"


def _correct_option(scenario: dict, step: dict, role: str) -> dict | None:
    """The option this role should have picked at this step (None when the role has no options)."""
    options = step.get("options", {}).get(_role_key(role), [])
    return next((o for o in options if o.get("correct") is True), None)


def results(scenario: dict, players: list[dict], answers: list[dict],
            restore_result: str | None = None,
            host_player_id: int | None = None,
            book: "object | None" = None,
            devices: list[dict] | None = None) -> dict:
    """The finished drill's ``DrillResults``.

    ``players``: one dict per joined player ({player_id, name, role}); ``answers``: one
    dict per recorded answer ({player_id, step_id, option_id, correct, action_ids}).
    A player with no answer for a step counts as wrong for it.

    The host runs the drill rather than being scored on it (the frozen
    ``drill_view_finished.json`` shows no host row): with ``host_player_id`` set the
    host gets no row, and the host's *unanswered* steps contribute nothing to the team
    tally - only the steps the host did answer count.

    ``book`` + ``devices`` (impact, T7.06): when both are given, each player's row also
    carries ``top_missed_impact`` - the highest impact of the steps they got wrong or
    skipped, so the end screen shows not just *how many* but *what* they overlooked.
    """
    from alerts import impact as _impact
    steps = scenario["steps"]
    by_key: dict[tuple[int, str], dict] = {(a["player_id"], a["step_id"]): a for a in answers}
    shown = [p for p in players if p["player_id"] != host_player_id]

    # --- per shown player: correct/total per phase, and the missed action IDs ----
    results_by_player = []
    for p in shown:
        pid, role = p["player_id"], p["role"]
        by_phase: dict[str, dict] = {}
        missed: list[str] = []
        top_missed_impact: int | None = None
        for step in steps:
            # One point is possible only if this player's role had options at this step.
            correct_opt = _correct_option(scenario, step, role)
            if correct_opt is None:
                continue
            phase = step["phase"]
            cell = by_phase.setdefault(phase, {"correct": 0, "total": 0})
            cell["total"] += 1
            ans = by_key.get((pid, step["step_id"]))
            if ans is not None and ans.get("correct"):
                cell["correct"] += 1
            else:
                # Wrong or missing: record the actions the right answer would have taken.
                for act in correct_opt.get("actions", []):
                    if act not in missed:
                        missed.append(act)
                # What this miss cost (T7.06): the step's weighted exposure.
                exposure = _impact.step_exposure(book, devices or [], step)
                if exposure and (top_missed_impact is None or exposure > top_missed_impact):
                    top_missed_impact = exposure
        results_by_player.append({
            "name": p["name"],
            # Only the phases this player actually faced appear.
            "by_phase": by_phase,
            "missed_actions": missed,
            "top_missed_impact": top_missed_impact,
        })

    # --- team tally: every options-step of every player; the host's unanswered
    # steps are excluded (they were never scored). -------------------------------
    team_correct = team_total = 0
    for step in steps:
        for p in players:
            if p["player_id"] == host_player_id and host_player_id is not None:
                if host_player_id not in {a["player_id"] for a in answers if a["step_id"] == step["step_id"]}:
                    continue          # host skipped this step: not part of the team score
            correct_opt = _correct_option(scenario, step, p["role"])
            if correct_opt is None:
                continue
            team_total += 1
            ans = by_key.get((p["player_id"], step["step_id"]))
            if ans is not None and ans.get("correct"):
                team_correct += 1

    return {
        "phases": PHASES,
        "players": results_by_player,
        "team": {"correct": team_correct, "total": team_total},
        "restore": None if restore_result is None else {"result": restore_result},
    }
