"""The 10-second background pass: unanswered proposals and expired blocks (T4.06-T4.08).

Reads time only from the ``Clock``, so tests run the 5-minute wait and the 1-hour expiry
in milliseconds with ``FakeClock.advance``.
"""
from __future__ import annotations

from actions import propose
from actions.wazuh_client import WazuhClient
from clock import Clock, iso, parse_iso
from config import Config
from db import Database, mark_device
from errors import ApiError


def run_once(db: Database, clock: Clock, config: Config, client: WazuhClient) -> dict:
    """One pass. Returns counts, e.g. ``{"executed": 1, "escalated": 0, "expired": 0}``."""
    out = {"executed": 0, "escalated": 0, "expired": 0}
    now = clock.now()
    now_text = iso(now)
    clinic = db.clinic()

    # 1. Proposals nobody answered within the approval wait.
    for row in db.query("SELECT * FROM actions WHERE status = 'proposed' ORDER BY id"):
        if now < propose.approval_deadline(row, clinic["approval_timeout_minutes"]):
            continue
        # Standing rule ON: block automatically and tell the owner (T4.06).
        if clinic["standing_rule_block_ip"]:
            try:
                propose.execute(db, clock, config, client, row, clinic["standing_rule_set_by"], "standing_rule")
            except ApiError as exc:                       # refused at the last re-check, or Wazuh down
                db.add_notification(f"ShieldMate couldn't block {row['target_ip']}: {exc.message}",
                                    now_text, alert_id=row["alert_id"], action_row_id=row["id"], to_role="owner")
            else:
                db.add_notification("Blocked under your standing rule.", now_text,
                                    alert_id=row["alert_id"], action_row_id=row["id"], to_role="owner")
                out["executed"] += 1
        # Standing rule OFF: leave it unexecuted and ask the backup approver instead (T4.07).
        elif _escalate(db, clinic, row, now_text):
            out["escalated"] += 1

    # 2. Blocks whose hour is up.
    for row in db.query("SELECT * FROM actions WHERE status = 'executed' AND expires_at <= ? ORDER BY id", (now_text,)):
        with db.transaction():
            db.execute("UPDATE actions SET status = 'expired' WHERE id = ?", (row["id"],))
            db.emit("action.expired", subject=("action", row["id"]), alert_id=row["alert_id"],
                    agent_name=row["agent_name"])
            if propose.active_block(db, row["agent_name"], now_text) is None:
                mark_device(db, row["agent_name"], "ok", now_text)
        out["expired"] += 1
    return out


def _escalate(db: Database, clinic: dict, action, now_text: str) -> bool:
    """Ask the backup approver, once per action, with the IT contact's number (decision 16).

    The note names the computer, because the backup approver may not see that alert's card (Ravi
    never gets RECEPTION-PC cards), and ``routes/notifications.py`` gives it the Block button.
    """
    backup = next((s for s in db.staff_list() if s["is_backup_approver"]), None)
    if backup is None:
        return False
    already = db.one("SELECT 1 FROM notifications WHERE action_row_id = ? AND to_staff_id = ?",
                     (action["id"], backup["id"]))
    if already:
        return False
    owner = next((s["name"] for s in db.staff_list() if s["role"] == "owner"), "The owner")
    db.add_notification(
        f"{owner} hasn't answered the request to block an attacker on {action['agent_name']}: please decide,"
        f" or call {clinic['it_contact_name']} on {clinic['it_contact_phone']}.",
        now_text, alert_id=action["alert_id"], action_row_id=action["id"], to_staff_id=backup["id"])
    waited = (parse_iso(now_text) - parse_iso(action["proposed_at"])).total_seconds()
    db.emit("action.escalated", subject=("action", action["id"]), alert_id=action["alert_id"],
            to_staff_id=backup["id"], waited_s=int(waited))
    return True
