"""GET /alerts, POST /alerts/{id}/done, POST /alerts/{id}/reword."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from alerts import pipeline
from contract import AlertOut, AlertsResponse, DoneRequest, Lang, RewordRequest, RewordResponse, Role
from errors import ApiError, require_flag
from lessons import reword as guard

router = APIRouter()


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(request: Request, role: Role, lang: Lang = "en"):
    ctx = request.app.state.ctx
    return pipeline.list_alerts(ctx.db, ctx.lessons, role, lang)


@router.post("/alerts/{alert_id}/done", response_model=AlertOut)
def post_done(alert_id: int, body: DoneRequest, request: Request, lang: Lang = "en"):
    ctx = request.app.state.ctx
    return pipeline.mark_done(ctx.db, ctx.clock, ctx.lessons, alert_id, body.staff_id, lang)


@router.post("/alerts/{alert_id}/reword", response_model=RewordResponse,
             dependencies=[Depends(require_flag("AI_REWORD"))])
def post_reword(alert_id: int, body: RewordRequest, request: Request):
    ctx = request.app.state.ctx
    row = ctx.db.one("SELECT * FROM alerts WHERE id = ? AND status != 'filtered'", (alert_id,))
    c = pipeline.card(ctx.lessons, row, body.role, body.lang) if row else None
    if c is None:
        raise ApiError("not_found", "No such alert.", 404)
    lesson = ctx.lessons.get(row["rule_id"])
    values = pipeline._values(ctx.lessons, lesson, row)
    # The provider only ever sees the two filled strings, never log_fields (T3.01).
    return guard.reword(ctx.reword_provider, c["headline"], c["why"], lesson, values)
