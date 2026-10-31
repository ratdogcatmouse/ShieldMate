"""v2: the IT support loop. The only writer of ``alert_it_log`` and the ``it_*``/``closed_*`` columns.

    staff tick "Call IT" (called) -> IT taps Call received (received) -> IT marks it
    resolved with what they did (resolved) -> the owner confirms (closed) or sends it
    back (received again, with the owner's reason).

IT can't close an incident; only the owner can, and only after IT says it's fixed. The
IT contact has no staff row, so their log lines have ``by_staff_id`` NULL. Notes are
free text from people: they go to the owner as notifications and back to screens as
plain text, never into the event log.
"""
from __future__ import annotations

from sqlite3 import Row

from actions import propose
from clock import Clock, now_iso
from db import Database, mark_device
from errors import ApiError

RESOLVED_NOTE_MIN = 5       # "Say what you did, so the owner can check it"


def log(db: Database, alert_id: int, at: str, kind: str, by_staff_id: int | None = None,
        note: str | None = None) -> None:
    db.execute("INSERT INTO alert_it_log (alert_id, at, kind, by_staff_id, note) VALUES (?,?,?,?,?)",
               (alert_id, at, kind, by_staff_id, note))


def it_out(db: Database, row: Row, called: Row | None) -> dict:
    """The ``ItOut`` shape. ``called`` is the alert's CALL_SAVED_IT step row, if ticked."""
    status = ("closed" if row["closed_at"] else "resolved" if row["it_resolved_at"]
              else "received" if row["it_received_at"] else "called" if called else "none")
    entries = db.query("SELECT * FROM alert_it_log WHERE alert_id = ? ORDER BY id", (row["id"],))
    return {
        "status": status,
        "called_by": called["done_by"] if called else None,
        "called_at": called["done_at"] if called else None,
        "received_at": row["it_received_at"],
        "resolved_at": row["it_resolved_at"],
        "resolved_note": row["it_resolved_note"],
        "sent_back_at": row["it_sent_back_at"],
        "sent_back_note": row["it_sent_back_note"],
        "closed_at": row["closed_at"],
        "closed_by": row["closed_by"],
        "log": [{"at": e["at"], "kind": e["kind"], "by_staff_id": e["by_staff_id"], "note": e["note"]}
                for e in entries],
    }


def _open_alert(db: Database, alert_id: int) -> Row:
    row = db.one("SELECT * FROM alerts WHERE id = ? AND status != 'filtered'", (alert_id,))
    if row is None:
        raise ApiError("not_found", "No such alert.", 404)
    if row["closed_at"] is not None:
        raise ApiError("already_closed", "The owner has already closed this one.", 409)
    return row


def it_action(db: Database, clock: Clock, alert_id: int, action: str, note: str) -> None:
    """The IT contact's panel: ``received`` (once), ``note``, or ``resolved`` with what fixed it."""
    row = _open_alert(db, alert_id)
    note = note.strip()
    now_text = now_iso(clock)
    it_name = db.clinic()["it_contact_name"]
    with db.transaction():
        if action == "received":
            if row["it_received_at"] is None:       # a second tap changes nothing
                db.execute("UPDATE alerts SET it_received_at = ? WHERE id = ?", (now_text, alert_id))
                log(db, alert_id, now_text, "received")
        elif action == "note":
            if not note:
                raise ApiError("invalid_request", "Write a note first.", 400)
            log(db, alert_id, now_text, "note", note=note)
        else:  # resolved
            if len(note) < RESOLVED_NOTE_MIN:
                raise ApiError("invalid_request", "Say what you did, so the owner can check it.", 400)
            # Resolving without tapping "received" first still counts as having picked it up.
            db.execute("UPDATE alerts SET it_received_at = COALESCE(it_received_at, ?), it_resolved_at = ?,"
                       " it_resolved_note = ? WHERE id = ?", (now_text, now_text, note, alert_id))
            log(db, alert_id, now_text, "resolved", note=note)
            db.add_notification(f"{it_name} says it's fixed: \"{note}\". Check and close it.", now_text,
                                alert_id=alert_id, to_role="owner")
        db.emit("alert.it", subject=("alert", alert_id), it_action=action)


def close(db: Database, clock: Clock, alert_id: int, staff_id: int, confirm: bool, note: str) -> None:
    """The owner checks IT's fix: ``confirm`` closes the incident, otherwise it goes back to IT.

    Closing withdraws any block request still waiting and, for a password attack with no
    block in force, puts the PC back to OK.
    """
    staff = db.staff(staff_id)
    if staff is None:
        raise ApiError("invalid_request", "Unknown staff member.", 400)
    if staff["role"] != "owner":
        raise ApiError("not_owner", "Only the owner can close an incident.", 403)
    row = _open_alert(db, alert_id)
    if row["it_resolved_at"] is None:
        raise ApiError("not_resolved", "IT hasn't marked this resolved yet.", 409)
    now_text = now_iso(clock)
    with db.transaction():
        if confirm:
            db.execute("UPDATE alerts SET closed_at = ?, closed_by = ? WHERE id = ?", (now_text, staff_id, alert_id))
            log(db, alert_id, now_text, "confirmed", staff_id)
            propose.withdraw_pending(db, alert_id, "closed")
            if row["rule_id"] == "60204" and propose.active_block(db, row["agent_name"], now_text) is None:
                mark_device(db, row["agent_name"], "ok", now_text)
        else:
            why = note.strip() or "Not fixed yet"
            db.execute("UPDATE alerts SET it_resolved_at = NULL, it_resolved_note = NULL, it_sent_back_at = ?,"
                       " it_sent_back_note = ? WHERE id = ?", (now_text, why, alert_id))
            log(db, alert_id, now_text, "sent_back", staff_id, why)
        db.emit("alert.closed", actor=staff_id, subject=("alert", alert_id), confirmed=confirm)
