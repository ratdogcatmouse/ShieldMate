"""GET /devices and the device-status seam the alert and action lanes call.

Status rules (T4.10): a new 60204 alert sets its device ``under_attack``; an executed
block sets ``protected``; expiry, undo or Done with no active block puts it back to
``ok``. The lanes never write ``devices`` themselves - they go through
``set_device_status`` (wired in by ``db.mark_device``), so this route file owns the
strip's state end to end.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from actions import propose
from clock import now_iso
from contract import DevicesResponse
from db import Database
from errors import require_flag

router = APIRouter()


def set_device_status(db: Database, agent_name: str, status: str, when: str) -> None:
    """Record a device's live-strip status, stamped with the caller's clock time.

    A no-op when nothing changed, so ``status_changed_at`` keeps the moment the strip
    last *moved* (a second "protected" event must not refresh the timestamp).
    """
    row = db.one("SELECT status FROM devices WHERE agent_name = ?", (agent_name,))
    if row is None or row["status"] == status:
        return
    db.execute("UPDATE devices SET status = ?, status_changed_at = ? WHERE agent_name = ?",
               (status, when, agent_name))


@router.get("/devices", response_model=DevicesResponse,
            dependencies=[Depends(require_flag("ACTIONS"))])
def get_devices(request: Request):
    """The owner's device strip; ``block`` names the executed, not-yet-expired block."""
    ctx = request.app.state.ctx
    db, clock = ctx.db, ctx.clock
    now_text = now_iso(clock)
    devices = []
    for d in db.devices():
        block_row = propose.active_block(db, d["agent_name"], now_text)
        devices.append({
            "id": d["id"],
            "agent_name": d["agent_name"],
            "location": d["location"],
            "status": d["status"],
            "status_changed_at": d["status_changed_at"],
            "block": None if block_row is None else {
                "action_row_id": block_row["id"],
                "target_ip": block_row["target_ip"],
                "expires_at": block_row["expires_at"],
            },
        })
    return {"devices": devices}
