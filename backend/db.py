"""SQLite access: one connection, schema, seed loader and reset.

One connection is shared across threads (``check_same_thread=False``) behind an RLock,
so the request handlers and the 10 s background task never interleave statements.
Writes go through ``transaction()``. Only the owning modules call this (routes never do SQL).
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config import Config

# Children first, so foreign keys never block a delete (T0.07).
RUNTIME_TABLES = [
    "actions", "drill_answers", "drill_players", "drills",
    "restore_runs", "notifications", "alerts",
]


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.lock = threading.RLock()
        # isolation_level=None: autocommit, so transactions are the explicit BEGIN below.
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._depth = 0

    # --- helpers -----------------------------------------------------------

    # Small wrappers over the single shared connection; every one takes the lock.

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: tuple | list = ()) -> int:
        """Run one write; returns lastrowid."""
        with self.lock:
            return self.conn.execute(sql, params).lastrowid

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """BEGIN/COMMIT (ROLLBACK on error). Nested use joins the outer transaction."""
        with self.lock:
            outer = self._depth == 0
            if outer:
                self.conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if outer:
                    self.conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outer:
                    self.conn.execute("COMMIT")

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    # --- setup tables and notifications (shared by several modules) -----------

    # Convenience readers/writers for the setup tables and notifications, shared across modules.

    def clinic(self) -> dict:
        row = dict(self.one("SELECT * FROM clinic WHERE id = 1"))
        row["never_block"] = json.loads(row["never_block"])
        return row

    def staff_list(self) -> list[dict]:
        return [dict(r) for r in self.query("SELECT * FROM staff ORDER BY id")]

    def staff(self, staff_id: int) -> dict | None:
        return row_to_dict(self.one("SELECT * FROM staff WHERE id = ?", (staff_id,)))

    def devices(self) -> list[dict]:
        out = []
        for r in self.query("SELECT * FROM devices ORDER BY id"):
            d = dict(r)
            d["services"] = json.loads(d["services"])
            d["when_down"] = json.loads(d["when_down"])
            out.append(d)
        return out

    def set_standing_rule(self, enabled: bool, staff_id: int, when: str) -> None:
        """Record the owner's standing rule and who/when set it (T4.09), on or off."""
        self.execute(
            "UPDATE clinic SET standing_rule_block_ip = ?, standing_rule_set_by = ?,"
            " standing_rule_set_at = ? WHERE id = 1", (int(enabled), staff_id, when))

    def add_notification(self, text: str, created_at: str, *, alert_id: int | None = None,
                         action_row_id: int | None = None, from_staff_id: int | None = None,
                         to_role: str | None = None, to_staff_id: int | None = None) -> int:
        return self.execute(
            "INSERT INTO notifications (alert_id, action_row_id, from_staff_id, to_role,"
            " to_staff_id, text, created_at) VALUES (?,?,?,?,?,?,?)",
            (alert_id, action_row_id, from_staff_id, to_role, to_staff_id, text, created_at))

    # --- schema, seed, reset -----------------------------------------------

    def init_schema(self, schema_path: Path) -> None:
        """Create the ten tables if the file is new (idempotent for an existing DB)."""
        with self.lock:
            has_tables = self.conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='clinic'"
            ).fetchone()[0]
            if not has_tables:
                self.conn.executescript(schema_path.read_text(encoding="utf-8"))

    def load_seed(self, seed_path: Path) -> None:
        """(Re)insert the setup tables from seed/clinic.json. Assumes they are empty."""
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        c = seed["clinic"]
        with self.transaction():
            for s in seed["staff"]:
                self.execute(
                    "INSERT INTO staff (id,name,role,can_restore_backups,can_approve_downtime,is_backup_approver)"
                    " VALUES (?,?,?,?,?,?)",
                    (s["id"], s["name"], s["role"], int(s["can_restore_backups"]),
                     int(s["can_approve_downtime"]), int(s["is_backup_approver"])))
            self.execute(
                "INSERT INTO clinic (id,name,backup_age_limit_hours,it_contact_name,it_contact_phone,"
                "approval_timeout_minutes,block_minutes,never_block) VALUES (1,?,?,?,?,?,?,?)",
                (c["name"], c["backup_age_limit_hours"], c["it_contact_name"], c["it_contact_phone"],
                 c["approval_timeout_minutes"], c["block_minutes"], json.dumps(c["never_block"])))
            for d in seed["devices"]:
                self.execute(
                    "INSERT INTO devices (agent_name,wazuh_agent_id,location,services,when_down)"
                    " VALUES (?,?,?,?,?)",
                    (d["agent_name"], d["wazuh_agent_id"], d["location"],
                     json.dumps(d["services"]), json.dumps(d["when_down"])))

    def reset(self, config: Config) -> None:
        """Back to the seeded clinic. Safe to run twice in a row (T0.07).

        Replay cursors live in the ReplaySource, so the demo route resets those too.
        """
        with self.transaction():
            # 1. Empty the runtime tables, children first so foreign keys never block.
            for table in RUNTIME_TABLES:
                self.execute(f"DELETE FROM {table}")
            # 2. Empty the setup tables (clinic points at staff, so clinic goes first) and re-seed them.
            for table in ("devices", "clinic", "staff"):
                self.execute(f"DELETE FROM {table}")
            self.load_seed(config.seed_path)
        # 3. Outside the DB: fresh synthetic backup (Lane 2's generator, if present) and an empty sandbox.
        _regenerate_backup()
        _empty_dir(config.restore_sandbox_dir)


def mark_device(db: Database, agent_name: str, status: str, when: str) -> None:
    """Set a device's live-strip status through Lane 2's ``routes.devices.set_device_status``.

    That helper belongs to the devices route owner; until it exists this is a no-op, so
    nothing in the alert/action lane breaks while the other lane is still being written.
    """
    try:
        from routes import devices
    except ImportError:
        return
    setter = getattr(devices, "set_device_status", None)
    if callable(setter):
        setter(db, agent_name, status, when)


def _regenerate_backup() -> None:
    """Ask the demo-backup generator (Lane 2) for a fresh synthetic backup, if it exists yet."""
    try:
        from demo_backup import make
    except ImportError:
        return
    ensure = getattr(make, "ensure", None)
    if callable(ensure):
        ensure(force=True)


def _empty_dir(path: Path) -> None:
    """Remove everything inside ``path`` (creating it if missing)."""
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def connect(config: Config) -> Database:
    """Open the DB, create the schema if needed and seed it if empty."""
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(config.db_path)
    db.init_schema(config.schema_path)
    if db.one("SELECT 1 FROM clinic") is None:
        db.load_seed(config.seed_path)
    return db


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)
