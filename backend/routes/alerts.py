"""GET /alerts, POST /alerts/{id}/done, POST /alerts/{id}/reword, and the v2 card routes:
PUT /alerts/{id}/steps/{action}, POST /alerts/{id}/mine|reopen|it|close."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from alerts import impact, it, pipeline
from contract import (ActionId, AlertOut, AlertsResponse, CloseRequest, DoneRequest, ItRequest, Lang,
                      RewordRequest, RewordResponse, Role, StepRequest)
from errors import ApiError, require_flag, require_owner
from lessons import reword as guard

router = APIRouter()


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(request: Request, role: Role, lang: Lang = "en",
               sort: Literal["time", "impact"] = Query("time"), include_closed: bool = False):
    ctx = request.app.state.ctx
    book = impact.book_for(ctx.config.seed_path)
    return pipeline.list_alerts(ctx.db, ctx.lessons, role, lang, book=book, sort=sort,
                                include_closed=include_closed)


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
    # Only an alert this role can see on its own list can be reworded for it.
    c = pipeline.card_for(ctx.lessons, row, body.role, body.lang,
                          impact.book_for(ctx.config.seed_path)) if row else None
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


# --- v2 ---------------------------------------------------------------------------
# Each answers with the alert in the acting person's wording (the IT panel and the owner's
# close get the owner's), so the screen can redraw from the response.

@router.put("/alerts/{alert_id}/steps/{action}", response_model=AlertOut)
def put_step(alert_id: int, action: ActionId, body: StepRequest, request: Request, lang: Lang = "en"):
    ctx = request.app.state.ctx
    book = impact.book_for(ctx.config.seed_path)
    return pipeline.set_step(ctx.db, ctx.clock, ctx.lessons, alert_id, action, body.staff_id, body.done,
                             lang, book=book)


@router.post("/alerts/{alert_id}/mine", response_model=AlertOut)
def post_mine(alert_id: int, body: DoneRequest, request: Request, lang: Lang = "en"):
    ctx = request.app.state.ctx
    book = impact.book_for(ctx.config.seed_path)
    return pipeline.say_mine(ctx.db, ctx.clock, ctx.lessons, alert_id, body.staff_id, lang, book=book)


@router.post("/alerts/{alert_id}/reopen", response_model=AlertOut)
def post_reopen(alert_id: int, body: DoneRequest, request: Request, lang: Lang = "en"):
    ctx = request.app.state.ctx
    book = impact.book_for(ctx.config.seed_path)
    return pipeline.reopen(ctx.db, ctx.clock, ctx.config, ctx.lessons, alert_id, body.staff_id, lang, book=book)


@router.post("/alerts/{alert_id}/it", response_model=AlertOut)
def post_it(alert_id: int, body: ItRequest, request: Request):
    """The clinic IT contact's panel. No staff id: the IT contact isn't a staff member."""
    ctx = request.app.state.ctx
    it.it_action(ctx.db, ctx.clock, alert_id, body.action, body.note)
    return pipeline.alert_out_for(ctx.db, ctx.lessons, alert_id, "owner", "en",
                                  book=impact.book_for(ctx.config.seed_path))


@router.post("/alerts/{alert_id}/close", response_model=AlertOut, dependencies=[Depends(require_owner)])
def post_close(alert_id: int, body: CloseRequest, request: Request):
    ctx = request.app.state.ctx
    it.close(ctx.db, ctx.clock, alert_id, body.staff_id, body.confirm, body.note)
    return pipeline.alert_out_for(ctx.db, ctx.lessons, alert_id, "owner", "en",
                                  book=impact.book_for(ctx.config.seed_path))
