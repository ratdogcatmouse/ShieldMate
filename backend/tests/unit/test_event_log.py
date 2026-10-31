"""The event log store and ``db.emit``: transactional, never raising, checked against the catalogue."""
import json
import logging
import sqlite3
import threading
from typing import get_args

import pytest

import db as database
from clock import FakeClock
from config import Config
from contract import ClientEventType
from eventlog import catalogue
from eventlog.log import EventLog, NullEventLog


@pytest.fixture
def db(tmp_path):
    d = database.connect(Config(db_path=tmp_path / "db.sqlite"))
    d.events = EventLog(tmp_path / "events.db", FakeClock())
    yield d
    d.close()
    d.events.close()


def rows(d) -> list[dict]:
    conn = sqlite3.connect(d.events.path)
    conn.row_factory = sqlite3.Row
    try:
        return [{**dict(r), "data": json.loads(r["data"])} for r in conn.execute("SELECT * FROM events ORDER BY id")]
    finally:
        conn.close()


def test_emit_records_one_row_with_the_actor_role(db):
    db.emit("alert.done", actor=1, subject=("alert", 7), rule_id="60204", lang="en", already_done=False)
    [ev] = rows(db)
    assert ev["type"] == "alert.done" and ev["origin"] == "server"
    assert (ev["actor_staff_id"], ev["actor_role"]) == (1, "front_desk")       # role looked up from staff
    assert (ev["subject_type"], ev["subject_id"]) == ("alert", "7")
    assert ev["ts"] == "2026-11-01T04:00:00Z" and ev["epoch"] == 0 and ev["run_id"] == db.events.run_id
    assert ev["data"] == {"rule_id": "60204", "lang": "en", "already_done": False}


def test_a_bare_database_records_nothing(tmp_path):
    d = database.connect(Config(db_path=tmp_path / "db.sqlite"))
    assert isinstance(d.events, NullEventLog)
    d.emit("system.stopped")                      # a no-op, not an error
    d.close()


def test_events_wait_for_commit_and_vanish_on_rollback(db):
    with db.transaction():
        db.emit("demo.reset", epoch=1)
        with db.transaction():                    # nested: joins the outer one
            db.emit("demo.reset", epoch=2)
        assert rows(db) == []                     # nothing written before COMMIT
    assert [e["data"]["epoch"] for e in rows(db)] == [1, 2]

    with pytest.raises(RuntimeError):
        with db.transaction():
            db.emit("demo.reset", epoch=3)
            raise RuntimeError
    assert [e["data"]["epoch"] for e in rows(db)] == [1, 2]    # the rolled-back write never shows

    db.emit("demo.reset", epoch=4)                # and the buffer was cleared, not carried over
    assert [e["data"]["epoch"] for e in rows(db)] == [1, 2, 4]


def test_another_threads_event_is_not_swept_into_a_rolled_back_transaction(db):
    other = threading.Thread(target=lambda: db.emit("system.stopped"))
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.emit("demo.reset", epoch=1)
            other.start()
            other.join(0.2)                       # blocked on the lock until this transaction ends
            raise RuntimeError
    other.join()
    assert [e["type"] for e in rows(db)] == ["system.stopped"]


def test_a_broken_log_never_raises(db, caplog):
    db.events.conn.close()
    with caplog.at_level(logging.ERROR, logger="shieldmate"):
        db.emit("system.stopped")
        db.events.bump_epoch()
    assert "event log write failed" in caplog.text


def test_unknown_types_and_keys_fail_loudly_in_server_code(db):
    with pytest.raises(AssertionError):
        db.emit("alert.deleted")
    with pytest.raises(AssertionError):
        db.emit("notification.sent", text="Meena handled: ...")        # free text is never a key


def test_client_data_is_trimmed_not_rejected():
    data = {"message": "x" * 500, "evil": 1, "path": "/staff/1"}
    assert catalogue.clean("ui.app_error", data, strict=False) == {"message": "x" * 200, "path": "/staff/1"}


def test_the_epoch_survives_a_restart(tmp_path):
    log = EventLog(tmp_path / "events.db", FakeClock())
    assert (log.bump_epoch(), log.bump_epoch()) == (1, 2)
    log.close()
    again = EventLog(tmp_path / "events.db", FakeClock())
    assert again.epoch == 2 and again.run_id != log.run_id
    again.close()


def test_contract_and_catalogue_list_the_same_client_events():
    assert set(get_args(ClientEventType)) == {t for t in catalogue.EVENT_TYPES if t.startswith("ui.")}


def test_no_catalogue_key_shadows_an_emit_keyword():
    # client.ingest splats cleaned client data into db.emit(**data).
    keys = {k for t in catalogue.EVENT_TYPES.values() for k in t.keys}
    assert not keys & {"type_", "actor", "subject", "origin", "session"}
