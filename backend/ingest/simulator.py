"""Tier-2 in-app attack simulator (roadmap T8): a multi-phase attacker that *generates*
Wazuh-shaped alerts in-process from an attack script. No lab needed.

It is an ``AlertSource`` (it implements ``next_batch``), so everything downstream -
normalise -> filter -> group -> cards -> actions - runs unchanged. The 5 s ingest loop in
``main._ingest_loop`` is the only caller of ``next_batch``; this module never reaches
Wazuh and never writes ``alerts`` / ``drill_answers`` - it *observes* the DB to decide the
branch, and the alert pipeline remains the sole writer of alert rows (the safety rule from
decision 12, carried over).

Time model. Each script carries ``sim_time_ms_multiplier`` (default 1). A phase with
``at_ms`` becomes due when the *real* clock has advanced ``at_ms * multiplier`` ms since
the run started - so the demo can be stretched into watchable minutes. Tests set the
multiplier to 1 and drive the ``FakeClock`` to fire phases on demand.

The branch. When the team's correct response lands - an executed ``BLOCK_IP`` against the
attacker IP, *or* the open drill's latest correct answer carrying ``ISOLATE_NETWORK`` - the
run's outcome becomes ``contained`` and every remaining ``cancel_if`` phase is skipped.
That is the "act fast, and the encrypt wave never happens" lesson: the end screen says
*contained in 4:12*, not *script finished*.

v4: a script may name ``contain_on``, the action IDs that stop it. For those scripts the
team also contains the attack the way non-technical staff actually respond - by ticking
that step on a card this run created - or by a correct drill answer carrying one of them
since the run started (and ``BLOCK_IP`` counts only if listed). The first such response is
latched as ``contained_by`` (what, who, when) for the results screen. Scripts without
``contain_on`` keep the original check exactly (decision: the rehearsed demos don't change).

Outcomes: ``running`` / ``contained`` / ``spread`` (no cancellable phase was skipped) /
``stopped`` (Backstage kill switch) / ``expired`` (the run outlived its sim time limit).
"""
from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from clock import Clock, iso, now_iso
from contract import ActionId
from db import Database
from ingest.source import RawAlert

_ACTION_IDS = set(get_args(ActionId))
# What stops a script that has no contain_on (the original check, unchanged).
_LEGACY_STOP = ["BLOCK_IP", "ISOLATE_NETWORK"]


class SimScriptError(ValueError):
    """The attack script breaks the T8 rules (unknown phases, negative times, ...)."""


class Simulator:
    """Owns the current run and yields its due phases as ``RawAlert``s.

    One instance lives on ``ctx.sim``; the ingest loop polls it and the demo routes
    call ``start`` / ``stop``. All progress is in-memory; the ``sim_runs`` row exists so
    the outcome survives a poll and so ``/demo/reset`` can clear it like any runtime table.
    """

    def __init__(self, config, db: Database, clock: Clock):
        self._db = db
        self._clock = clock
        self._config = config
        self._lock = threading.Lock()
        self._run: dict | None = None        # the current/last run, in memory
        self._next_run_id = 1

    # --- script loading ------------------------------------------------------

    def _load_script(self, script_id: str) -> dict:
        path = Path(self._config.sim_dir) / f"{script_id}.json"
        if not path.is_file():
            raise SimScriptError(f"unknown script {script_id!r}")
        script = json.loads(path.read_text(encoding="utf-8"))
        self._validate(script)
        return script

    @staticmethod
    def _validate(script: dict) -> None:
        for key in ("id", "phases"):
            if key not in script:
                raise SimScriptError(f"script missing {key!r}")
        phases = script["phases"]
        if not isinstance(phases, list) or not phases:
            raise SimScriptError("script has no phases")
        last = -1
        for i, phase in enumerate(phases):
            at_ms = phase.get("at_ms")
            if not isinstance(at_ms, (int, float)) or at_ms < 0:
                raise SimScriptError(f"phase {i}: at_ms must be a non-negative number")
            if at_ms < last:
                raise SimScriptError(f"phase {i}: at_ms must be non-decreasing")
            last = at_ms
            alert = phase.get("alert") or {}
            if not (alert.get("rule", {}).get("id") and alert.get("agent", {}).get("name")):
                raise SimScriptError(f"phase {i}: alert needs rule.id and agent.name")
        mult = script.get("sim_time_ms_multiplier", 1)
        if not isinstance(mult, (int, float)) or mult <= 0:
            raise SimScriptError("sim_time_ms_multiplier must be a positive number")
        contain_on = script.get("contain_on")
        if contain_on is not None and (not isinstance(contain_on, list) or not contain_on
                                       or not set(contain_on) <= _ACTION_IDS):
            raise SimScriptError("contain_on must be a non-empty list of action IDs")

    # --- start / stop --------------------------------------------------------

    def start(self, script_id: str) -> dict:
        """Create a run for ``script_id`` and return the start result (SimStartResult body)."""
        script = self._load_script(script_id)
        multiplier = int(script.get("sim_time_ms_multiplier", 1))
        limit_ms = int(self._config.sim_time_limit_ms)
        total_ms = max((int(p["at_ms"]) for p in script["phases"]), default=0)
        with self._lock:
            self._run = {
                "id": self._next_run_id,
                "script_id": script["id"],
                "phases": script["phases"],
                "attacker": script.get("attacker") or {},
                "multiplier": multiplier,
                "limit_ms": limit_ms,
                "title": script.get("title", script_id),
                "contain_on": script.get("contain_on"),   # None = the original check
                "contained_by": None,                     # {action, staff_id, at} once contained
                "real_total_ms": total_ms * multiplier,
                "fired_hi": 0,          # index of the first phase not yet emitted
                "fired": 0,             # phases actually emitted
                "cancelled": 0,         # cancel_if phases skipped (the branch)
                "status": "running",
                "reason": None,
                "started_at": now_iso(self._clock),
                "started_dt": self._clock.now(),
                "finished_at": None,
                "finished_dt": None,
            }
            run_id = self._db.execute(
                "INSERT INTO sim_runs (script_id, status, started_at) VALUES (?, 'running', ?)",
                (script["id"], self._run["started_at"]))
            self._run["id"] = run_id if run_id else self._next_run_id
            self._next_run_id = max(self._next_run_id, self._run["id"] + 1)
            result = {"run": self._run_out_locked(), "title": self._run["title"],
                      "real_total_ms": self._run["real_total_ms"]}
        return result

    def stop(self) -> dict | None:
        """Backstage kill switch: the run ends now, whatever is left."""
        with self._lock:
            if self._run is None or self._run["status"] != "running":
                return self._run_out_locked()
            self._finish(self._run, "stopped", "stopped by Backstage")
        return self.run_out()

    def reset_state(self) -> None:
        """Called by /demo/reset: drop the in-memory run (the sim_runs row is emptied by the DB)."""
        with self._lock:
            self._run = None
            self._next_run_id = 1

    # --- AlertSource ---------------------------------------------------------

    def next_batch(self, alert_type: str | None = None) -> list[RawAlert]:
        """Due phases only. Advances the run's progress; terminal runs yield nothing.

        The branch is per-phase (roadmap 1.2): a ``cancel_if: CONTAINED`` phase is
        *skipped* when the team's response has landed, but later phases without
        ``cancel_if`` still fire (an encrypt wave already running keeps going). When the
        last phase is resolved the outcome is ``contained`` iff any cancellable phase was
        skipped, else ``spread`` - or ``stopped``/``expired`` for the kill switch / limit.
        """
        with self._lock:
            run = self._run
            if run is None or run["status"] != "running":
                return []
            elapsed = self._elapsed_ms(run)
            now_dt = self._clock.now()
            phases = run["phases"]
            # v4 scripts latch the first response on every poll, so a tick that is later
            # unticked (or a drill that moves on) still counts: the team did act in time.
            if run["contain_on"] is not None and run["contained_by"] is None:
                run["contained_by"] = self._contained_by_v4(run)
            batch: list[RawAlert] = []
            i = run["fired_hi"]
            while i < len(phases):
                phase = phases[i]
                if int(phase["at_ms"]) * run["multiplier"] > elapsed:
                    break                                # not yet due; phases are time-ordered
                if phase.get("cancel_if") == "CONTAINED" and self._contained(run):
                    run["cancelled"] += 1                # escalation avoided
                    i += 1
                    continue
                batch.append(self._raw_alert(phase, i, run, now_dt))
                i += 1
                run["fired"] += 1
            run["fired_hi"] = i

            # Terminal: every phase resolved, or the window is up with some left.
            if run["fired_hi"] >= len(phases) or elapsed >= run["limit_ms"]:
                if run["cancelled"]:
                    self._finish(run, "contained", f"team contained it; {run['cancelled']} escalation(s) avoided")
                elif run["fired_hi"] < len(phases):
                    self._finish(run, "expired", f"time limit ({run['limit_ms']} ms) reached, {len(phases) - run['fired_hi']} phase(s) left")
                else:
                    self._finish(run, "spread", f"all {len(phases)} phases fired")
            return batch

    def _raw_alert(self, phase: dict, i: int, run: dict, now_dt) -> RawAlert:
        """One phase as a ``RawAlert``: a copy of its alert, stamped, with a deduped external_id."""
        alert = copy.deepcopy(phase["alert"])
        alert["timestamp"] = now_iso(now_dt)             # stamp "now" like the replay source
        sm = phase.get("shieldmate")
        if sm:
            alert["shieldmate"] = sm                      # normalise() reads the counts from here
        return {
            "source": "wazuh",
            "external_id": f"sim:{run['id']}:{i}",        # the pipeline's dedupe catches double ticks
            "alert": alert,
            "shieldmate": sm,
        }

    def _finish(self, run: dict, status: str, reason: str) -> None:
        run["status"] = status
        run["reason"] = reason
        run["finished_dt"] = self._clock.now()
        run["finished_at"] = iso(run["finished_dt"])
        self._db.execute(
            "UPDATE sim_runs SET status = ?, outcome_reason = ?, finished_at = ? WHERE id = ?",
            (status, reason, run["finished_at"], run["id"]))

    def _elapsed_ms(self, run: dict) -> int:
        return int((self._clock.now() - run["started_dt"]).total_seconds() * 1000)

    # --- the containment check (read-only, the branch condition) -------------

    def _contained(self, run: dict) -> bool:
        """The branch condition for a due ``cancel_if`` phase."""
        if run["contain_on"] is not None:
            return run["contained_by"] is not None
        found = self._is_contained(run)
        if found is not None and run["contained_by"] is None:
            run["contained_by"] = found                 # for the results screen only
        return found is not None

    def _is_contained(self, run: dict) -> dict | None:
        """The original check (scripts without ``contain_on``), unchanged in what it accepts.
        Returns who/what/when for the results screen, or None."""
        db = self._db
        attacker_ip = (run["attacker"] or {}).get("ip")
        # (a) An executed BLOCK_IP against the attacker's address.
        if attacker_ip:
            found = self._executed_block(attacker_ip)
            if found is not None:
                return found
        # (b) The open drill's latest correct answer carried ISOLATE_NETWORK.
        drill = db.one("SELECT code FROM drills WHERE status='open' LIMIT 1")
        if drill is not None:
            ans = db.one("SELECT a.action_ids, a.answered_at, p.staff_id FROM drill_answers a"
                         " JOIN drill_players p ON p.id = a.player_id"
                         " WHERE a.drill_code=? AND a.correct=1"
                         " ORDER BY a.answered_at DESC LIMIT 1", (drill["code"],))
            if ans is not None:
                ids = json.loads(ans["action_ids"] or "[]")
                if "ISOLATE_NETWORK" in ids:
                    return {"action": "ISOLATE_NETWORK", "staff_id": ans["staff_id"], "at": ans["answered_at"]}
        return None

    def _executed_block(self, attacker_ip: str) -> dict | None:
        row = self._db.one(
            "SELECT decided_by, decided_at FROM actions WHERE action_id='BLOCK_IP' AND status='executed'"
            " AND target_ip=? ORDER BY decided_at LIMIT 1", (attacker_ip,))
        if row is None:
            return None
        # decided_at is always set by actions/*, but a hand-edited row may lack it: then "now".
        return {"action": "BLOCK_IP", "staff_id": row["decided_by"],
                "at": row["decided_at"] or now_iso(self._clock)}

    def _contained_by_v4(self, run: dict) -> dict | None:
        """v4: the earliest response naming one of the script's ``contain_on`` actions.

        (a) a step ticked on a card this run created (its alerts carry ``sim:{run}:`` ids);
        (b) a correct drill answer carrying one, given since the run started;
        (c) an executed ``BLOCK_IP`` on the attacker, only when the script lists BLOCK_IP.
        """
        db = self._db
        stop = list(run["contain_on"])
        marks = ",".join("?" for _ in stop)
        found: list[dict] = []
        tick = db.one(
            f"SELECT s.action, s.done_by, s.done_at FROM alert_steps s JOIN alerts a ON a.id = s.alert_id"
            f" WHERE a.external_id LIKE ? AND s.action IN ({marks}) ORDER BY s.done_at LIMIT 1",
            (f"sim:{run['id']}:%", *stop))
        if tick is not None:
            found.append({"action": tick["action"], "staff_id": tick["done_by"], "at": tick["done_at"]})
        for ans in db.query(
                "SELECT a.action_ids, a.answered_at, p.staff_id FROM drill_answers a"
                " JOIN drill_players p ON p.id = a.player_id"
                " WHERE a.correct=1 AND a.answered_at >= ? ORDER BY a.answered_at", (run["started_at"],)):
            hit = next((x for x in json.loads(ans["action_ids"] or "[]") if x in stop), None)
            if hit is not None:
                found.append({"action": hit, "staff_id": ans["staff_id"], "at": ans["answered_at"]})
                break
        attacker_ip = (run["attacker"] or {}).get("ip")
        if "BLOCK_IP" in stop and attacker_ip:
            block = self._executed_block(attacker_ip)
            if block is not None:
                found.append(block)
        return min(found, key=lambda f: f["at"] or "") if found else None

    # --- observation ---------------------------------------------------------

    def run_out(self) -> dict | None:
        with self._lock:
            return self._run_out_locked()

    def summary(self) -> dict | None:
        """v4: the ``SimSummary`` on GET /status - what the team sees about the latest run
        (its title, the outcome, what stopped it or what would have). None before any run."""
        with self._lock:
            run = self._run
            if run is None:
                return None
            out = self._run_out_locked()
            stop = list(run["contain_on"]) if run["contain_on"] is not None else list(_LEGACY_STOP)
            return {
                "script_id": out["script_id"],
                "title": run["title"],
                "status": out["status"],
                "started_at": out["started_at"],
                "finished_at": out["finished_at"],
                "elapsed_ms": out["elapsed_ms"],
                "phases_fired": out["phases_fired"],
                "phases_cancelled": out["phases_cancelled"],
                "stop_actions": stop,
                "contained_by": dict(run["contained_by"]) if run["contained_by"] else None,
            }

    def _run_out_locked(self) -> dict | None:
        run = self._run
        if run is None:
            return None
        finished_dt = run["finished_dt"] or (self._clock.now() if run["status"] == "running" else run["started_dt"])
        elapsed = int((finished_dt - run["started_dt"]).total_seconds() * 1000)
        return {
            "id": run["id"],
            "script_id": run["script_id"],
            "status": run["status"],
            "outcome_reason": run["reason"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "phases_fired": run["fired"],
            "phases_cancelled": run["cancelled"],
            "elapsed_ms": elapsed,
        }
