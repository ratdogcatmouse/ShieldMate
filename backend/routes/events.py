"""POST /events: the phones' batched UI events, for the event log (flag EVENT_LOG)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from contract import EventsAccepted, EventsRequest
from errors import require_flag
from eventlog import client

router = APIRouter()


@router.post("/events", response_model=EventsAccepted,
             dependencies=[Depends(require_flag("EVENT_LOG"))])
def post_events(body: EventsRequest, request: Request):
    ctx = request.app.state.ctx
    return {"accepted": client.ingest(ctx.db, body.session_id, body.events)}
