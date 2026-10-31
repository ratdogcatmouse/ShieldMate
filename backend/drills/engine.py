"""Drill engine: sessions, the lobby/open/review/finished state machine, and answers.

The server owns all drill state (design doc: phones only render ``GET /drills/{code}``
and post answers, so two phones and a laptop stay in agreement with 2 s polling).
This module is the only writer of the drill tables; routes call it, never SQL.

    lobby --advance--> open s1 --auto/advance--> review s1
          --advance--> open s2 ... --advance--> finished

Non-host advance is ``not_host``. A drill option that names BLOCK_IP is practice,
never a real action: drill answers only write ``drill_answers``, so nothing in the
approval flow (``actions/``) can be triggered by a drill (T4.11).
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from sqlite3 import Row

from clock import Clock, now_iso
from db import Database
from drills import models, scoring
from errors import ApiError

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


class ScenarioRegistry:
    """Loaded scenario files, keyed by scenario_id (re-loadable so tests can swap content)."""

    def __init__(self, dir_path: Path = SCENARIOS_DIR, reload: bool = False):
        if not hasattr(self, "_by_id") or reload:
            self._by_id = models.load_scenarios(dir_path)

    def get(self, scenario_id: str) -> dict:
        return self._by_id[scenario_id]

    def has(self, scenario_id: str) -> bool:
        return scenario_id in self._by_id


_REGISTRY: "ScenarioRegistry | None" = None


def registry() -> ScenarioRegistry:
    """The process-wide registry (built once; tests can rebuild by passing their own)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ScenarioRegistry()
    return _REGISTRY


# --- small reads the view and mutations share ---------------------------------

def _drill_row(db: Database, code: str) -> Row:
    row = db.one("SELECT * FROM drills WHERE code = ?", (code,))
    if row is None:
        raise ApiError("drill_not_found", "No open drill with that code.", 404)
    return row


def _players(db: Database, code: str) -> list[dict]:
    rows = db.query(
        "SELECT p.*, s.name AS staff_name, s.role AS staff_role FROM drill_players p"
        " JOIN staff s ON s.id = p.staff_id WHERE p.drill_code = ? ORDER BY p.id", (code,))
    return [{"player_id": r["id"], "staff_id": r["staff_id"], "name": r["staff_name"],
             "role": r["staff_role"], "joined_at": r["joined_at"]} for r in rows]


def _answers(db: Database, code: str, step_id: str | None = None) -> list[dict]:
    """Stored answers, with ``action_ids`` decoded; a closed step may hold empty-text rows."""
    rows = db.query(
        "SELECT * FROM drill_answers WHERE drill_code = ?" + ("" if step_id is None else " AND step_id = ?"),
        (code, step_id) if step_id is not None else (code,))
    return [{**dict(r), "action_ids": json.loads(r["action_ids"])} for r in rows]


def _role_key(role: str) -> str:
    """front_desk/billing share the scenario's "staff" options; the owner gets "owner"."""
    return "owner" if role == "owner" else "staff"


def _step(row: Row, scenario: dict) -> dict | None:
    """The step the drill is on (or the last one once finished, for the results view)."""
    idx = max(0, min(row["step_index"], len(scenario["steps"]) - 1))
    return scenario["steps"][idx]


def _steps_with_options(step: dict, players: list[dict]) -> list[dict]:
    """The joined players whose role has options at this step - exactly who must answer (T1.10)."""
    return [p for p in players if step.get("options", {}).get(_role_key(p["role"]), [])]


def _insert_answer(db: Database, code: str, player_id: int, step_id: str, option_id: str,
                   action_ids: list[str], correct: int, at: str) -> None:
    db.execute(
        "INSERT INTO drill_answers (drill_code, player_id, step_id, option_id, action_ids, correct, answered_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (code, player_id, step_id, option_id, json.dumps(action_ids), correct, at))


# --- create / join -------------------------------------------------------------

def create(db: Database, clock: Clock, scenario_id: str, host_staff_id: int,
           source_alert_id: int | None = None,
           reg: ScenarioRegistry | None = None) -> dict:
    """New drill: a 4-digit code, unique among the open ones; the host joins automatically."""
    reg = reg or registry()
    if not reg.has(scenario_id):
        raise ApiError("invalid_request", f"Unknown scenario {scenario_id!r}.", 400)
    if db.staff(host_staff_id) is None:
        raise ApiError("invalid_request", "Unknown staff member.", 400)
    if source_alert_id is not None and db.one("SELECT 1 FROM alerts WHERE id = ?", (source_alert_id,)) is None:
        raise ApiError("invalid_request", "Unknown source alert.", 400)
    open_codes = {r["code"] for r in db.query(
        "SELECT code FROM drills WHERE status IN ('lobby','open','review')")}
    code = f"{random.randint(0, 9999):04d}"
    while code in open_codes:                       # unique among open drills (T1.05)
        code = f"{random.randint(0, 9999):04d}"
    now_text = now_iso(clock)
    db.execute(
        "INSERT INTO drills (code, scenario_id, status, step_index, host_staff_id, source_alert_id, created_at)"
        " VALUES (?,?,'lobby',-1,?,?,?)",
        (code, scenario_id, host_staff_id, source_alert_id, now_text))
    db.execute("INSERT INTO drill_players (drill_code, staff_id, joined_at) VALUES (?,?,?)",
               (code, host_staff_id, now_text))
    player_id = db.one("SELECT id FROM drill_players WHERE drill_code = ? AND staff_id = ?",
                       (code, host_staff_id))["id"]
    return {"code": code, "player_id": player_id, "status": "lobby"}


def join(db: Database, clock: Clock, code: str, staff_id: int) -> dict:
    """Join by staff_id; the same staff_id again returns the same player_id (decision 14),
    so a phone that reloads mid-drill carries on instead of duplicating itself."""
    row = _drill_row(db, code)
    if row["status"] == "finished":
        raise ApiError("drill_finished", "This drill is already finished.", 409)
    if db.staff(staff_id) is None:
        raise ApiError("invalid_request", "Unknown staff member.", 400)
    existing = db.one("SELECT id FROM drill_players WHERE drill_code = ? AND staff_id = ?",
                      (code, staff_id))
    if existing:
        return {"player_id": existing["id"], "code": code, "status": row["status"]}
    player_id = db.execute("INSERT INTO drill_players (drill_code, staff_id, joined_at) VALUES (?,?,?)",
                           (code, staff_id, now_iso(clock)))
    return {"player_id": player_id, "code": code, "status": row["status"]}


# --- answers ---------------------------------------------------------------------

def answer(db: Database, clock: Clock, code: str, player_id: int, step_id: str, option_id: str,
           reg: ScenarioRegistry | None = None) -> dict:
    """Lock one answer; the player's own feedback shows immediately.

    A second answer is ``already_answered`` and never changes the score (T1.07); an answer
    after the step closed is ``step_closed``; an option the role was not offered is
    ``invalid_option``.
    """
    reg = reg or registry()
    row = _drill_row(db, code)
    if row["status"] == "finished":
        raise ApiError("drill_finished", "This drill is already finished.", 409)
    if row["status"] != "open":
        # Lobby, review and finished all read as "closed" to a phone that is behind.
        raise ApiError("step_closed", "This step has already closed, so your answer was not counted.", 409)
    scenario = reg.get(row["scenario_id"])
    step = _step(row, scenario)
    if step["step_id"] != step_id:
        raise ApiError("step_closed", "That step is not the current one.", 409)
    player = db.one("SELECT p.staff_id, s.role AS staff_role FROM drill_players p"
                    " JOIN staff s ON s.id = p.staff_id WHERE p.drill_code = ? AND p.id = ?",
                    (code, player_id))
    if player is None:
        raise ApiError("player_not_in_drill", "That player is not in this drill.", 404)
    options = step.get("options", {}).get(_role_key(player["staff_role"]), [])
    if not any(o["option_id"] == option_id for o in options):
        raise ApiError("invalid_option", "That option is not offered to your role.", 400)
    if db.one("SELECT 1 FROM drill_answers WHERE drill_code = ? AND player_id = ? AND step_id = ?",
              (code, player_id, step_id)):
        raise ApiError("already_answered", "You already answered this step.", 409)
    opt = next(o for o in options if o["option_id"] == option_id)
    with db.transaction():
        _insert_answer(db, code, player_id, step_id, option_id, opt.get("actions", []),
                       int(opt.get("correct", False)), now_iso(clock))
        _auto_close(db, row, step)
    return {"option_id": option_id, "correct": bool(opt.get("correct", False)),
            "feedback": opt.get("feedback", ""), "actions": opt.get("actions", [])}


def _auto_close(db: Database, row: Row, step: dict) -> None:
    """The step closes itself when everyone who has options has answered (T1.10)."""
    if all(p["player_id"] in {a["player_id"] for a in _answers(db, row["code"], step["step_id"])}
           for p in _steps_with_options(step, _players(db, row["code"]))):
        db.execute("UPDATE drills SET status = 'review' WHERE code = ?", (row["code"],))


# --- advance (host only) ----------------------------------------------------------

def advance(db: Database, clock: Clock, code: str, player_id: int,
            reg: ScenarioRegistry | None = None) -> dict:
    """One button, four moves:

    lobby -> open step 1;  open -> review (closes the step early; non-answers count as
    wrong);  review -> open next step;  review on the last step -> finished.

    Only the drill's host may call it; a finished drill is ``drill_finished``.
    """
    reg = reg or registry()
    row = _drill_row(db, code)
    if row["status"] == "finished":
        raise ApiError("drill_finished", "This drill is already finished.", 409)
    player = db.one("SELECT * FROM drill_players WHERE drill_code = ? AND id = ?", (code, player_id))
    if player is None:
        raise ApiError("player_not_in_drill", "That player is not in this drill.", 404)
    if row["host_staff_id"] != player["staff_id"]:
        raise ApiError("not_host", "Only the drill host can move the team on.", 403)
    scenario = reg.get(row["scenario_id"])
    now_text = now_iso(clock)
    with db.transaction():
        if row["status"] == "lobby":
            db.execute("UPDATE drills SET status = 'open', step_index = 0, step_opened_at = ? WHERE code = ?",
                       (now_text, code))
        elif row["status"] == "open":
            # Owner closes early: unanswered options-havers are recorded as wrong with no option.
            step = _step(row, scenario)
            answered = {a["player_id"] for a in _answers(db, code, step["step_id"])}
            for p in _steps_with_options(step, _players(db, code)):
                if p["player_id"] not in answered:
                    _insert_answer(db, code, p["player_id"], step["step_id"], "", [], 0, now_text)
            db.execute("UPDATE drills SET status = 'review' WHERE code = ?", (code,))
        else:  # review
            if row["step_index"] >= len(scenario["steps"]) - 1:
                db.execute("UPDATE drills SET status = 'finished' WHERE code = ?", (code,))
            else:
                db.execute("UPDATE drills SET status = 'open', step_index = step_index + 1,"
                           " step_opened_at = ? WHERE code = ?", (now_text, code))
    return view(db, code, player_id, reg)


# --- the shared drill view ----------------------------------------------------------

def view(db: Database, code: str, player_id: int, reg: ScenarioRegistry | None = None) -> dict:
    """One response shape for every device; fields that don't apply are null.

    Options never carry ``correct``/``feedback``/``actions`` until that player has
    answered, so a phone can't peek at the answer key.
    """
    reg = reg or registry()
    row = _drill_row(db, code)
    player = db.one(
        "SELECT p.id AS pid, p.staff_id, s.name AS staff_name, s.role AS staff_role"
        " FROM drill_players p JOIN staff s ON s.id = p.staff_id WHERE p.drill_code = ? AND p.id = ?",
        (code, player_id))
    if player is None:
        raise ApiError("player_not_in_drill", "That player is not in this drill.", 404)
    role = player["staff_role"]
    is_host = row["host_staff_id"] == player["staff_id"]
    scenario = reg.get(row["scenario_id"])
    finished = row["status"] == "finished"
    # The view's step: the current one when open/review; None in the lobby and when finished.
    step = None if finished or row["status"] == "lobby" else _step(row, scenario)
    # Impact always reflects the step being shown; a finished drill keeps its last step's picture.
    impact_step = scenario["steps"][-1] if finished else step
    showing_step = step is not None and row["status"] in ("open", "review")

    # This player's options for the step (text only - the answer key stays hidden).
    options = [{"option_id": o["option_id"], "text": o["text"]}
               for o in step.get("options", {}).get(_role_key(role), [])] if showing_step else []

    # My locked answer, with the feedback that is now safe to show.
    my_answer = None
    if showing_step:
        mine = next((a for a in _answers(db, code, step["step_id"]) if a["player_id"] == player_id), None)
        if mine is not None:
            opt = next((o for o in step.get("options", {}).get(_role_key(role), [])
                        if o["option_id"] == mine["option_id"]), {})
            my_answer = {"option_id": mine["option_id"], "correct": bool(mine["correct"]),
                         "feedback": opt.get("feedback", ""), "actions": mine["action_ids"]}

    # Team progress: total counts only the players who have options this step (T1.10).
    team_players = []
    team_answered = 0
    if showing_step:
        answers = {a["player_id"]: a for a in _answers(db, code, step["step_id"])}
        for p in _players(db, code):
            has = bool(step.get("options", {}).get(_role_key(p["role"]), []))
            answered = has and p["player_id"] in answers
            team_answered += int(answered)
            team_players.append({"player_id": p["player_id"], "name": p["name"], "role": p["role"],
                                 "has_options": has, "answered": answered})
    team = {"answered": team_answered,
            "total": sum(1 for p in team_players if p["has_options"]),
            "players": team_players}

    # In review, everyone sees who chose what; a null option_text is "no answer".
    review = None
    if row["status"] == "review" and step is not None:
        answers = {a["player_id"]: a for a in _answers(db, code, step["step_id"])}
        answers_list = []
        for p in _players(db, code):
            opts = step.get("options", {}).get(_role_key(p["role"]), [])
            if not opts:
                continue
            a = answers.get(p["player_id"])
            opt = next((o for o in opts if o["option_id"] == a["option_id"]), None) if a else None
            answers_list.append({"name": p["name"], "option_text": opt["text"] if opt else None,
                                 "correct": bool(a["correct"]) if a else False})
        review = {"answers": answers_list}

    # "Run restore check" appears for the host once they picked the trigger option (T1.16).
    restore_available = False
    if is_host and showing_step:
        host_ans = next((a for a in _answers(db, code, step["step_id"])
                         if a["player_id"] == _player_id_for_staff(db, code, row["host_staff_id"])), None)
        host_opt = next((o for o in step.get("options", {}).get("owner", [])
                         if host_ans and o["option_id"] == host_ans["option_id"]), None)
        if host_opt and "restore_check" in (host_opt.get("triggers") or []):
            restore_available = True

    # Finished: results per phase, missed actions, and the latest restore outcome.
    # The host runs the drill (host_player_id) and is not scored on it - the frozen
    # finished view shows no host row and the team tally counts only answered steps.
    results = None
    if finished:
        all_answers: list[dict] = []
        for s in scenario["steps"]:
            all_answers.extend(_answers(db, code, s["step_id"]))
        latest = db.one("SELECT result FROM restore_runs ORDER BY id DESC LIMIT 1")
        host_pid = _player_id_for_staff(db, code, row["host_staff_id"])
        results = scoring.results(scenario, _players(db, code), all_answers,
                                  restore_result=latest["result"] if latest else None,
                                  host_player_id=host_pid)

    return {
        "code": code,
        "scenario_id": row["scenario_id"],
        "title": scenario["title"],
        "status": row["status"],
        "step_index": row["step_index"],
        "step_count": len(scenario["steps"]),
        "me": {"player_id": player_id, "staff_id": player["staff_id"], "name": player["staff_name"],
               "role": role, "is_host": is_host},
        "step": None if step is None else {
            "step_id": step["step_id"], "phase": step["phase"], "game_time": step["game_time"],
            "situation": step["situation"], "opened_at": row["step_opened_at"]},
        "options": options,
        "waiting_message": "Waiting for the team to decide"
        if (showing_step and not options) else None,
        "my_answer": my_answer,
        "team": team,
        "review": review,
        "impact": [] if impact_step is None else _impact(db, impact_step),
        "restore_check_available": restore_available,
        # The host moves the team from the lobby (to open s1), can close any open step
        # early, and walks review -> next step -> finished.
        "can_advance": is_host and row["status"] in ("lobby", "open", "review"),
        "results": results,
    }


def _impact(db: Database, step: dict) -> list[dict]:
    from drills import impact as impact_mod
    return impact_mod.step_impact(step, db.devices())


def _player_id_for_staff(db: Database, code: str, staff_id: int) -> int | None:
    r = db.one("SELECT id FROM drill_players WHERE drill_code = ? AND staff_id = ?", (code, staff_id))
    return r["id"] if r else None
