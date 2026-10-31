"""The ``actions`` table: proposals and every decision on them. Nothing else writes it.

Lifecycle: ``proposed`` -> ``executed`` (approve, or the standing rule on timeout) or
``declined``; ``executed`` -> ``expired`` (timeout.py) or ``undone``; ``refused`` and
``failed`` are terminal. A *simulated* action (its alert came from replay, decision 12)
never reaches the Wazuh client, even in live mode.

``expires_at`` is the *block's* expiry and stays NULL until the action executes. The
approval deadline is ``proposed_at + approval_timeout_minutes``.
"""
from __future__ import annotations

import json
from datetime import timedelta
from sqlite3 import Row

from actions.targets import check_target
from actions.wazuh_client import UndoNotSupported, WazuhClient, WazuhUnavailable
from clock import Clock, iso, now_iso, parse_iso
from config import Config
from db import Database, mark_device
from errors import ApiError


def label_for(ip: str | None, block_minutes: int) -> str:
    return f"Block {ip} for {block_minutes} minutes" if ip else "Block the source address"


def approval_deadline(row: Row, approval_timeout_minutes: int):
    return parse_iso(row["proposed_at"]) + timedelta(minutes=approval_timeout_minutes)


def propose(db: Database, clock: Clock, alert_id: int, source: str, agent_name: str,
            ip: str | None) -> int:
    """Create the BLOCK_IP proposal for a new alert. A bad target is stored as ``refused`` (decision 17)."""
    ok, reason = check_target(ip, db.clinic()["never_block"])
    return db.execute(
        "INSERT INTO actions (alert_id, action_id, target_ip, agent_name, simulated, status,"
        " refused_reason, proposed_at) VALUES (?, 'BLOCK_IP', ?, ?, ?, ?, ?, ?)",
        (alert_id, ip, agent_name, int(source == "replay"),
         "proposed" if ok else "refused", reason, now_iso(clock)))


def get(db: Database, action_id: int) -> Row:
    row = db.one("SELECT * FROM actions WHERE id = ?", (action_id,))
    if row is None:
        raise ApiError("not_found", "No such action.", 404)
    return row


def active_block(db: Database, agent_name: str, now_text: str) -> Row | None:
    """An executed, not-yet-expired block on this device, if any."""
    return db.one(
        "SELECT * FROM actions WHERE agent_name = ? AND status = 'executed'"
        " AND expires_at > ? ORDER BY id DESC LIMIT 1", (agent_name, now_text))


def execute(db: Database, clock: Clock, config: Config, client: WazuhClient, row: Row,
            staff_id: int | None, via: str) -> Row:
    """Carry out a proposed block. Re-checks the target, then blocks (live) or just records it (simulated).

    Raises ``target_refused`` (409) or ``wazuh_unavailable`` (502); in both cases the row is
    updated first (``refused`` / ``failed``) so the log shows what happened.
    """
    now = clock.now()
    clinic = db.clinic()
    # Block A: safety re-check at execution time (the list could have changed since proposing).
    ok, reason = check_target(row["target_ip"], clinic["never_block"])
    if not ok:
        db.execute("UPDATE actions SET status='refused', refused_reason=? WHERE id=?", (reason, row["id"]))
        raise ApiError("target_refused", f"ShieldMate won't block that address: {reason}.", 409)

    # Block B: the only place a block can reach Wazuh. Simulated (replayed) alerts skip it entirely,
    # which is the safety rule from decision 12.
    response: dict = {"simulated": True}
    failure: ApiError | None = None
    if not row["simulated"]:
        device = db.one("SELECT wazuh_agent_id FROM devices WHERE agent_name = ?", (row["agent_name"],))
        try:
            response = client.block_ip(device["wazuh_agent_id"] if device else "", row["target_ip"])
        except WazuhUnavailable:
            failure = ApiError("wazuh_unavailable", "Wazuh didn't answer, so nothing was blocked.", 502)
            response = {"error": "wazuh_unavailable"}

    # Block C: record the outcome first (failed, or executed with the block's expiry and the device
    # turned "protected"), then raise any error, so the action log always shows what happened.
    with db.transaction():
        if failure:
            db.execute(
                "UPDATE actions SET status='failed', decided_by=?, decided_via=?, decided_at=?,"
                " wazuh_response=? WHERE id=?",
                (staff_id, via, iso(now), json.dumps(response), row["id"]))
        else:
            db.execute(
                "UPDATE actions SET status='executed', decided_by=?, decided_via=?, decided_at=?,"
                " expires_at=?, wazuh_response=? WHERE id=?",
                (staff_id, via, iso(now), iso(now + timedelta(minutes=clinic["block_minutes"])),
                 json.dumps(response), row["id"]))
            mark_device(db, row["agent_name"], "protected", iso(now))
    if failure:
        raise failure
    return get(db, row["id"])


# --- owner decisions: approve / decline / undo (called by routes/actions.py) ---

def _require_staff(db: Database, staff_id: int) -> None:
    if db.staff(staff_id) is None:
        raise ApiError("invalid_request", "Unknown staff member.", 400)


def approve(db: Database, clock: Clock, config: Config, client: WazuhClient,
            action_id: int, staff_id: int) -> Row:
    _require_staff(db, staff_id)
    row = get(db, action_id)
    if row["status"] != "proposed":
        raise ApiError("action_not_pending", "This request has already been answered.", 409)
    return execute(db, clock, config, client, row, staff_id, "tap")


def decline(db: Database, clock: Clock, action_id: int, staff_id: int) -> Row:
    _require_staff(db, staff_id)
    row = get(db, action_id)
    if row["status"] != "proposed":
        raise ApiError("action_not_pending", "This request has already been answered.", 409)
    db.execute("UPDATE actions SET status='declined', decided_by=?, decided_via='tap', decided_at=?"
               " WHERE id=?", (staff_id, now_iso(clock), action_id))
    return get(db, action_id)


def undo(db: Database, clock: Clock, config: Config, client: WazuhClient,
         action_id: int, staff_id: int) -> Row:
    _require_staff(db, staff_id)
    row = get(db, action_id)
    if not config.undo_supported or row["status"] != "executed":
        raise ApiError("undo_not_supported", "This block can't be undone from ShieldMate.", 409)
    if not row["simulated"]:
        device = db.one("SELECT wazuh_agent_id FROM devices WHERE agent_name = ?", (row["agent_name"],))
        try:
            client.unblock_ip(device["wazuh_agent_id"] if device else "", row["target_ip"])
        except UndoNotSupported:
            raise ApiError("undo_not_supported", "This block can't be undone from ShieldMate.", 409)
        except WazuhUnavailable:
            raise ApiError("wazuh_unavailable", "Wazuh didn't answer, so the block is still in place.", 502)
    now = now_iso(clock)
    with db.transaction():
        db.execute("UPDATE actions SET status='undone' WHERE id=?", (action_id,))
        if active_block(db, row["agent_name"], now) is None:
            mark_device(db, row["agent_name"], "ok", now)
    return get(db, action_id)


# --- reads -------------------------------------------------------------------

def view(db: Database, row: Row, config: Config, clock: Clock, clinic: dict | None = None) -> dict:
    """One row as the ``ActionOut`` shape. ``wazuh_response`` is stored but never returned."""
    clinic = clinic or db.clinic()
    seconds_left = None
    if row["status"] == "proposed":
        left = (approval_deadline(row, clinic["approval_timeout_minutes"]) - clock.now()).total_seconds()
        seconds_left = max(0, int(left))
    return {
        "id": row["id"],
        "alert_id": row["alert_id"],
        "action_id": row["action_id"],
        "label": label_for(row["target_ip"], clinic["block_minutes"]),
        "target_ip": row["target_ip"],
        "agent_name": row["agent_name"],
        "simulated": bool(row["simulated"]),
        "status": row["status"],
        "refused_reason": row["refused_reason"],
        "decided_by": row["decided_by"],
        "decided_via": row["decided_via"],
        "proposed_at": row["proposed_at"],
        "decided_at": row["decided_at"],
        "expires_at": row["expires_at"],
        "seconds_left": seconds_left,
        "on_timeout": "block_under_standing_rule" if clinic["standing_rule_block_ip"] else "ask_backup_approver",
        "undo_available": bool(config.undo_supported and row["status"] == "executed"),
    }


def list_actions(db: Database, config: Config, clock: Clock, status: str | None = None) -> list[dict]:
    """Newest first. With ``status`` set, only that status (``proposed`` = pending approval cards)."""
    clinic = db.clinic()
    rows = (db.query("SELECT * FROM actions WHERE status = ? ORDER BY id DESC", (status,))
            if status else db.query("SELECT * FROM actions ORDER BY id DESC"))
    return [view(db, r, config, clock, clinic) for r in rows]
