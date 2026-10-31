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

Outcomes: ``running`` / ``contained`` / ``spread`` (no cancellable phase was skipped) /
``stopped`` (Backstage kill switch) / ``expired`` (the run outlived its sim time limit).
"""
from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from clock import Clock, iso, now_iso
from db import Database
from ingest.source import RawAlert


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
            batch: list[RawAlert] = []
            i = run["fired_hi"]
            while i < len(phases):
                phase = phases[i]
                if int(phase["at_ms"]) * run["multiplier"] > elapsed:
                    break                                # not yet due; phases are time-ordered
                if phase.get("cancel_if") == "CONTAINED" and self._is_contained(run):
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

    def _is_contained(self, run: dict) -> bool:
        db = self._db
        attacker_ip = (run["attacker"] or {}).get("ip")
        # (a) An executed BLOCK_IP against the attacker's address.
        if attacker_ip:
            row = db.one(
                "SELECT 1 FROM actions WHERE action_id='BLOCK_IP' AND status='executed' AND target_ip=?",
                (attacker_ip,))
            if row is not None:
                return True
        # (b) The open drill's latest correct answer carried ISOLATE_NETWORK.
        drill = db.one("SELECT code FROM drills WHERE status='open' LIMIT 1")
        if drill is not None:
            ans = db.one("SELECT action_ids FROM drill_answers WHERE drill_code=? AND correct=1"
                         " ORDER BY answered_at DESC LIMIT 1", (drill["code"],))
            if ans is not None:
                ids = json.loads(ans["action_ids"] or "[]")
                if "ISOLATE_NETWORK" in ids:
                    return True
        return False

    # --- observation ---------------------------------------------------------

    def run_out(self) -> dict | None:
        with self._lock:
            return self._run_out_locked()

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
