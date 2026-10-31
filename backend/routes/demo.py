"""POST /demo/replay/{alert_type} and POST /demo/reset (Backstage)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from alerts import pipeline
from alerts.normalise import normalise
from clock import now_iso
from contract import ReplayResult, ResetResult
from errors import ApiError, require_backstage
from ingest.replay import ReplayExhausted

router = APIRouter(dependencies=[Depends(require_backstage)])


@router.post("/demo/replay/{alert_type}", response_model=ReplayResult)
def post_replay(alert_type: str, request: Request):
    ctx = request.app.state.ctx
    # Replay always uses the replay source, even in live mode, so the stage fallback works.
    replay = ctx.replay
    if alert_type not in replay.types:
        raise ApiError("invalid_request", f"Unknown alert type {alert_type!r}.", 400)
    try:
        click, batch = replay.next_click(alert_type)
    except ReplayExhausted:
        raise ApiError("replay_exhausted", "No more of these to replay. Press Reset.", 409)

    # Push every record of this click through the full pipeline and count what happened to each.
    tally = {"created": 0, "grouped": 0, "filtered": 0}
    now = now_iso(ctx.clock)
    for raw in batch:
        outcome = pipeline.process(normalise(raw, now), ctx.db, ctx.clock,
                                   lessons=ctx.lessons, config=ctx.config)
        tally[outcome] += 1
    return {
        "alert_type": alert_type,
        "click": click,
        "injected": len(batch),
        "cards_created": tally["created"],
        "grouped": tally["grouped"],
        "filtered": tally["filtered"],
        "clicks_left": replay.clicks_left(alert_type),
    }


@router.post("/demo/reset", response_model=ResetResult)
def post_reset(request: Request):
    ctx = request.app.state.ctx
    ctx.db.reset(ctx.config)
    ctx.replay.reset_state()
    return {"ok": True, "reset_at": now_iso(ctx.clock)}
