"""POST /demo/replay/{alert_type}, POST /demo/reset, POST /demo/skip (v2), and the attack-simulation routes (T8)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from actions import timeout
from alerts import pipeline
from alerts.normalise import normalise
from clock import now_iso
from contract import ReplayResult, ResetResult, SimStartResult, SimStatusResult, SkipRequest, SkipResult
from errors import ApiError, require_backstage, require_flag
from ingest.replay import ReplayExhausted
from ingest.simulator import SimScriptError

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
    result = {
        "alert_type": alert_type,
        "click": click,
        "injected": len(batch),
        "cards_created": tally["created"],
        "grouped": tally["grouped"],
        "filtered": tally["filtered"],
        "clicks_left": replay.clicks_left(alert_type),
    }
    ctx.db.emit("demo.replay", **{k: v for k, v in result.items() if k != "clicks_left"})
    return result


@router.post("/demo/reset", response_model=ResetResult)
def post_reset(request: Request):
    ctx = request.app.state.ctx
    ctx.clock.reset()                  # undo any "Skip 5 min" before the fresh clinic is stamped
    ctx.db.reset(ctx.config)
    ctx.replay.reset_state()
    if ctx.sim is not None:            # the simulator's in-memory run is dropped; sim_runs cleared by the DB
        ctx.sim.reset_state()
    return {"ok": True, "reset_at": now_iso(ctx.clock)}


@router.post("/demo/skip", response_model=SkipResult)
def post_skip(body: SkipRequest, request: Request):
    """v2: move the server clock forward, e.g. past the 5-minute approval wait so the standing rule acts.

    The timeout pass runs straight away, so the screens show the outcome on their next poll.
    """
    ctx = request.app.state.ctx
    ctx.clock.skip(body.minutes)
    ctx.db.emit("demo.skip", minutes=body.minutes, offset_minutes=ctx.clock.offset_minutes)
    timeout.run_once(ctx.db, ctx.clock, ctx.config, ctx.wazuh)
    return {"offset_minutes": ctx.clock.offset_minutes, "server_time": now_iso(ctx.clock)}


# --- Attack simulation (T8): Backstage presses Play, the script runs in the background. ---
# Route order matters: the literal /stop must be registered before /{script_id} or it is
# matched by the path param (Starlette routes in registration order).

_SIM_DEPENDS = [Depends(require_flag("SIMULATE"))]


@router.post("/demo/simulate/stop", response_model=SimStatusResult, dependencies=_SIM_DEPENDS)
def post_simulate_stop(request: Request):
    ctx = request.app.state.ctx
    if ctx.sim is None:
        raise ApiError("invalid_request", "Simulation is not enabled.", 400)
    return {"run": ctx.sim.stop()}


@router.post("/demo/simulate/{script_id}", response_model=SimStartResult, dependencies=_SIM_DEPENDS)
def post_simulate_start(script_id: str, request: Request):
    ctx = request.app.state.ctx
    sim = ctx.sim
    if sim is None:
        raise ApiError("invalid_request", "Simulation is not enabled.", 400)
    # Only one run at a time: a running attack has to be stopped or let finish first.
    current = sim.run_out()
    if current is not None and current["status"] == "running":
        raise ApiError("invalid_request", "A simulation is already running.", 409)
    try:
        return sim.start(script_id)
    except SimScriptError as exc:
        raise ApiError("invalid_request", str(exc), 400)


@router.get("/demo/simulate", response_model=SimStatusResult, dependencies=_SIM_DEPENDS)
def get_simulate(request: Request):
    ctx = request.app.state.ctx
    if ctx.sim is None:
        raise ApiError("invalid_request", "Simulation is not enabled.", 400)
    return {"run": ctx.sim.run_out()}
