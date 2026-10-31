"""The /drills routes: create, join, the shared view, answers and the host's advance.

The routes are thin - all state lives in ``drills.engine`` (the only writer of the
drill tables), so a phone and the owner laptop always see the same picture.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from contract import (AnswerRequest, AdvanceRequest, DrillCreateRequest, DrillCreateResponse,
                      DrillView, JoinRequest, JoinResponse, MyAnswer)
from drills import engine
from errors import require_owner

router = APIRouter()


@router.post("/drills", response_model=DrillCreateResponse, dependencies=[Depends(require_owner)])
def post_drills(body: DrillCreateRequest, request: Request):
    """Owner starts a drill (drill panel, or "Practise this with the team" on a handled alert)."""
    ctx = request.app.state.ctx
    return engine.create(ctx.db, ctx.clock, body.scenario_id, body.host_staff_id,
                         source_alert_id=body.source_alert_id)


@router.post("/drills/{code}/join", response_model=JoinResponse)
def post_join(code: str, body: JoinRequest, request: Request):
    ctx = request.app.state.ctx
    return engine.join(ctx.db, ctx.clock, code, body.staff_id)


@router.get("/drills/{code}", response_model=DrillView)
def get_drill(request: Request, code: str, player_id: int = Query(...)):
    ctx = request.app.state.ctx
    return engine.view(ctx.db, code, player_id)


@router.post("/drills/{code}/answers", response_model=MyAnswer)
def post_answer(code: str, body: AnswerRequest, request: Request):
    ctx = request.app.state.ctx
    return engine.answer(ctx.db, ctx.clock, code, body.player_id, body.step_id, body.option_id)


@router.post("/drills/{code}/advance", response_model=DrillView, dependencies=[Depends(require_owner)])
def post_advance(code: str, body: AdvanceRequest, request: Request):
    """The host-only move: lobby -> open, open -> review, review -> next step or finished."""
    ctx = request.app.state.ctx
    return engine.advance(ctx.db, ctx.clock, code, body.player_id)
