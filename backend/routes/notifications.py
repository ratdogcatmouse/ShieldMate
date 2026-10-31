"""GET /notifications: what's new for a role or a person, oldest first, by id cursor (decision 15)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from actions import propose
from contract import NotificationsResponse, Role
from errors import ApiError

router = APIRouter()


@router.get("/notifications", response_model=NotificationsResponse)
def get_notifications(request: Request, role: Role | None = None, staff_id: int | None = None,
                      since_id: int = 0):
    if role is None and staff_id is None:
        raise ApiError("invalid_request", "Send a role or a staff_id.", 400)
    db = request.app.state.ctx.db
    rows = db.query(
        "SELECT n.*, s.name AS from_name FROM notifications n"
        " LEFT JOIN staff s ON s.id = n.from_staff_id"
        " WHERE n.id > ? AND (n.to_role = ? OR n.to_staff_id = ?) ORDER BY n.id",
        (since_id, role, staff_id))
    quick = _quick_actions(request.app.state.ctx, rows)
    notes = [{
        "id": r["id"],
        "alert_id": r["alert_id"],
        "action_row_id": r["action_row_id"],
        "from_staff": None if r["from_staff_id"] is None else {"id": r["from_staff_id"], "name": r["from_name"]},
        "to_role": r["to_role"],
        "to_staff_id": r["to_staff_id"],
        "kind": r["kind"],
        "text": r["text"],
        "created_at": r["created_at"],
        "quick_action": quick.get(r["id"]),
    } for r in rows]
    if notes:
        last_id = notes[-1]["id"]
    else:
        # Nothing new: report the table's newest id (0 when empty). After a reset this drops
        # below the phone's stored cursor, which is the signal for it to start again.
        last_id = db.one("SELECT COALESCE(MAX(id), 0) AS m FROM notifications")["m"]
    return {"notifications": notes, "last_id": last_id}


def _quick_actions(ctx, rows) -> dict[int, dict]:
    """v3: the Block button for each ``attack`` note that points at a live BLOCK_IP request, by note id.

    Needs ACTIONS on (the actions routes are off without it). Only proposed, executed and expired
    requests are offered; a refused, declined or withdrawn one, or one with no source IP
    (ransomware), gets no button. Plain ``info`` notes never do, even where they point at an action
    (the standing-rule and escalation notes).
    """
    wanted = {r["id"]: r["action_row_id"] for r in rows if r["kind"] == "attack" and r["action_row_id"]}
    if not ctx.config.actions or not wanted:
        return {}
    ids = sorted(set(wanted.values()))
    actions = {a["id"]: a for a in ctx.db.query(
        f"SELECT id, target_ip, status FROM actions WHERE id IN ({','.join('?' * len(ids))})", ids)}
    minutes = ctx.db.clinic()["block_minutes"]
    out = {}
    for note_id, action_id in wanted.items():
        a = actions.get(action_id)
        if a is None or a["target_ip"] is None or a["status"] not in ("proposed", "executed", "expired"):
            continue
        out[note_id] = {"action_row_id": a["id"], "action": "BLOCK_IP",
                        "label": propose.label_for(a["target_ip"], minutes), "target_ip": a["target_ip"],
                        "minutes": minutes, "status": a["status"]}
    return out
