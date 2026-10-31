"""GET /alerts, POST /alerts/{id}/done, POST /alerts/{id}/reword."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from alerts import impact, pipeline
from contract import AlertOut, AlertsResponse, DoneRequest, Lang, RewordRequest, RewordResponse, Role
from errors import ApiError, require_flag
from lessons import reword as guard

router = APIRouter()


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(request: Request, role: Role, lang: Lang = "en",
               sort: Literal["time", "impact"] = Query("time")):
    ctx = request.app.state.ctx
    book = impact.book_for(ctx.config.seed_path)
    return pipeline.list_alerts(ctx.db, ctx.lessons, role, lang, book=book, sort=sort)


@router.post("/alerts/{alert_id}/done", response_model=AlertOut)
def post_done(alert_id: int, body: DoneRequest, request: Request, lang: Lang = "en"):
    ctx = request.app.state.ctx
    book = impact.book_for(ctx.config.seed_path)
    return pipeline.mark_done(ctx.db, ctx.clock, ctx.lessons, alert_id, body.staff_id, lang, book=book)


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
    result = guard.reword(ctx.reword_provider, c["headline"], c["why"], lesson, values)
    # Which way it went, never the wording itself.
    ctx.db.emit("alert.reworded", subject=("alert", alert_id), role=body.role, lang=body.lang,
                source=result["source"])
    return result
