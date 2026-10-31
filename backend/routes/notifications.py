"""GET /notifications: what's new for a role or a person, oldest first, by id cursor (decision 15)."""
from __future__ import annotations

from fastapi import APIRouter, Request

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
    notes = [{
        "id": r["id"],
        "alert_id": r["alert_id"],
        "action_row_id": r["action_row_id"],
        "from_staff": None if r["from_staff_id"] is None else {"id": r["from_staff_id"], "name": r["from_name"]},
        "to_role": r["to_role"],
        "to_staff_id": r["to_staff_id"],
        "text": r["text"],
        "created_at": r["created_at"],
    } for r in rows]
    if notes:
        last_id = notes[-1]["id"]
    else:
        # Nothing new: report the table's newest id (0 when empty). After a reset this drops
        # below the phone's stored cursor, which is the signal for it to start again.
        last_id = db.one("SELECT COALESCE(MAX(id), 0) AS m FROM notifications")["m"]
    return {"notifications": notes, "last_id": last_id}
