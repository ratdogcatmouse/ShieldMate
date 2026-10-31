"""GET /clinic, GET /status, PUT /clinic/standing-rule."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from clock import now_iso
from contract import ClinicOut, ClinicResponse, StandingRuleRequest, StatusResponse
from errors import ApiError, require_flag, require_owner

router = APIRouter()

# capability -> label shown on the owner screen (T2.08)
CAPABILITIES = {
    "can_restore_backups": "Restore backups",
    "can_approve_downtime": "Approve downtime",
}


def clinic_out(clinic: dict) -> dict:
    return {
        "id": clinic["id"],
        "name": clinic["name"],
        "backup_age_limit_hours": clinic["backup_age_limit_hours"],
        "it_contact_name": clinic["it_contact_name"],
        "it_contact_phone": clinic["it_contact_phone"],
        "standing_rule_block_ip": bool(clinic["standing_rule_block_ip"]),
        "standing_rule_set_by": clinic["standing_rule_set_by"],
        "standing_rule_set_at": clinic["standing_rule_set_at"],
        "approval_timeout_minutes": clinic["approval_timeout_minutes"],
        "block_minutes": clinic["block_minutes"],      # never_block stays on the server
    }


def single_points_of_failure(staff: list[dict]) -> list[dict]:
    """A capability only one person has is a single point of failure."""
    out = []
    for capability, label in CAPABILITIES.items():
        holders = [s["name"] for s in staff if s[capability]]
        if len(holders) == 1:
            out.append({"capability": capability, "label": label, "only": holders[0]})
    return out


@router.get("/clinic", response_model=ClinicResponse)
def get_clinic(request: Request):
    db = request.app.state.ctx.db
    staff = db.staff_list()
    return {
        "clinic": clinic_out(db.clinic()),
        "staff": [{**s, **{k: bool(s[k]) for k in
                           ("can_restore_backups", "can_approve_downtime", "is_backup_approver")}}
                  for s in staff],
        "devices": [{"id": d["id"], "agent_name": d["agent_name"], "location": d["location"],
                     "services": d["services"]} for d in db.devices()],
        "single_point_of_failure": single_points_of_failure(staff),
    }


@router.put("/clinic/standing-rule", response_model=ClinicOut,
            dependencies=[Depends(require_flag("ACTIONS")), Depends(require_owner)])
def put_standing_rule(body: StandingRuleRequest, request: Request):
    ctx = request.app.state.ctx
    if ctx.db.staff(body.staff_id) is None:
        raise ApiError("invalid_request", "Unknown staff member.", 400)
    ctx.db.set_standing_rule(body.enabled, body.staff_id, now_iso(ctx.clock))
    return clinic_out(ctx.db.clinic())


@router.get("/status", response_model=StatusResponse)
def get_status(request: Request):
    ctx = request.app.state.ctx
    return {
        "alert_source": ctx.config.alert_source,
        "flags": {"AI_REWORD": ctx.config.ai_reword, "ACTIONS": ctx.config.actions,
                  "SIMULATE": ctx.config.simulate},
        "undo_supported": ctx.config.undo_supported,
        "server_time": now_iso(ctx.clock),
        "wazuh": ctx.wazuh_health,       # all null in replay mode
    }
