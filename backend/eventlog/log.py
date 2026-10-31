"""The event log store: its own SQLite file, one append-only ``events`` table.

Nothing outside db.py calls this directly; code records events with ``db.emit(...)``,
which holds them back until a transaction commits (see ``Database.emit``).

Recording never raises: a full disk or a locked file must not fail a request or stop a
background loop, so failures go to the server log and the event is lost.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from clock import Clock, now_iso

log = logging.getLogger("shieldmate")

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Set per /api request by eventlog/middleware.py; they flow into the route's thread.
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
session_id: ContextVar[str | None] = ContextVar("session_id", default=None)


@dataclass
class Event:
    type: str
    ts: str
    epoch: int
    origin: str = "server"
    actor_staff_id: int | None = None
    actor_role: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    data: dict = field(default_factory=dict)


class EventLog:
    enabled = True

    def __init__(self, path: Path | str, clock: Clock, run_id: str | None = None):
        self.path = str(path)
        self.clock = clock
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.lock = threading.Lock()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        # Losing the last few events in a power cut is fine; slowing every request down is not.
        self.conn.execute("PRAGMA synchronous = NORMAL")
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'epoch'").fetchone()
        self.epoch = int(row[0]) if row else 0

    def event(self, type_: str, *, origin: str = "server", actor_staff_id: int | None = None,
              actor_role: str | None = None, subject: tuple[str, object] | None = None,
              session: str | None = None, data: dict | None = None) -> Event:
        """Stamp an event now: server time, the current epoch and the request's ids."""
        return Event(
            type=type_, ts=now_iso(self.clock), epoch=self.epoch, origin=origin,
            actor_staff_id=actor_staff_id, actor_role=actor_role,
            subject_type=subject[0] if subject else None,
            subject_id=None if not subject or subject[1] is None else str(subject[1]),
            request_id=request_id.get(), session_id=session or session_id.get(), data=data or {})

    def record(self, ev: Event) -> None:
        """Append one event. Never raises."""
        try:
            with self.lock:
                self.conn.execute(
                    "INSERT INTO events (ts, type, origin, actor_staff_id, actor_role, subject_type,"
                    " subject_id, request_id, session_id, run_id, epoch, data) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ev.ts, ev.type, ev.origin, ev.actor_staff_id, ev.actor_role, ev.subject_type,
                     ev.subject_id, ev.request_id, ev.session_id, self.run_id, ev.epoch,
                     json.dumps(ev.data, default=str)))
        except Exception:
            log.exception("event log write failed (%s)", ev.type)

    def bump_epoch(self) -> int:
        """A demo reset happened: later events belong to the next epoch (ids start from 1 again)."""
        try:
            with self.lock:
                self.conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('epoch', ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(self.epoch + 1),))
                self.epoch += 1
        except Exception:
            log.exception("event log epoch update failed")
        return self.epoch

    def close(self) -> None:
        with self.lock:
            self.conn.close()


class NullEventLog:
    """The default on a bare ``Database`` (unit tests, EVENT_LOG=0): records nothing."""
    enabled = False
    epoch = 0
    run_id = None

    def record(self, ev: Event) -> None:
        pass

    def bump_epoch(self) -> int:
        return 0

    def close(self) -> None:
        pass
