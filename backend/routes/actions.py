"""GET /actions and the owner's approve / decline / undo. All 404 ``not_enabled`` while ACTIONS is off."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from actions import propose
from contract import ActionDecisionRequest, ActionOut, ActionsResponse, ActionStatus
from errors import require_flag, require_owner

router = APIRouter(dependencies=[Depends(require_flag("ACTIONS"))])


def _out(ctx, row) -> dict:
    return propose.view(ctx.db, row, ctx.config, ctx.clock)


@router.get("/actions", response_model=ActionsResponse)
def get_actions(request: Request, status: ActionStatus | None = None):
    ctx = request.app.state.ctx
    return {"actions": propose.list_actions(ctx.db, ctx.config, ctx.clock, status)}


@router.post("/actions/{action_id}/approve", response_model=ActionOut, dependencies=[Depends(require_owner)])
def approve(action_id: int, body: ActionDecisionRequest, request: Request):
    ctx = request.app.state.ctx
    return _out(ctx, propose.approve(ctx.db, ctx.clock, ctx.config, ctx.wazuh, action_id, body.staff_id))


@router.post("/actions/{action_id}/decline", response_model=ActionOut, dependencies=[Depends(require_owner)])
def decline(action_id: int, body: ActionDecisionRequest, request: Request):
    ctx = request.app.state.ctx
    return _out(ctx, propose.decline(ctx.db, ctx.clock, action_id, body.staff_id))


@router.post("/actions/{action_id}/undo", response_model=ActionOut, dependencies=[Depends(require_owner)])
def undo(action_id: int, body: ActionDecisionRequest, request: Request):
    ctx = request.app.state.ctx
    return _out(ctx, propose.undo(ctx.db, ctx.clock, ctx.config, ctx.wazuh, action_id, body.staff_id))
