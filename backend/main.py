"""The FastAPI app: routers under /api, background tasks, and the built frontend.

Run with ``uvicorn main:app`` from backend/ (single worker, no --reload: the background
tasks must run exactly once). The real-vs-fake choices are made once, here (spec: "main.py
picks the real or fake implementation from config once at start-up").
"""
from __future__ import annotations

import asyncio
import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import db as database
from actions import timeout
from actions.wazuh_client import FakeWazuhClient
from alerts import pipeline
from alerts.normalise import normalise
from clock import Clock, RealClock, now_iso
from config import Config, Context
from errors import ApiError, install_handlers
from eventlog.log import EventLog
from eventlog.middleware import RequestEvents
from ingest.replay import ReplaySource
from lessons.engine import LessonBook
from lessons.providers import get_provider

log = logging.getLogger("shieldmate")

TIMEOUT_TICK_SECONDS = 10      # approval timeout / expiry pass
INGEST_TICK_SECONDS = 5        # live Wazuh poll

# Routers owned by the other backend lane. Mounted only if they exist yet.
LANE_TWO_ROUTERS = ("drills", "restore", "devices")
LANE_ONE_ROUTERS = ("clinic", "alerts", "notifications", "actions", "demo", "events")


def _optional(module: str, attr: str):
    """Look up ``attr`` in a module another owner may not have written yet."""
    try:
        return getattr(importlib.import_module(module), attr, None)
    except ImportError:
        return None


def _ensure_demo_backup(config: Config) -> None:
    """Build the synthetic backup if it is missing, so the restore check works before the first Reset.

    Only for the demo layout; a RESTORE_BACKUP_DIR pointing elsewhere is a real backup and is left alone.
    """
    try:
        from demo_backup import make
    except ImportError:
        return
    if config.restore_backup_dir == make.BACKUP_DIR:
        make.ensure()


def build_context(config: Config, clock: Clock, wazuh_client=None, source=None,
                  reword_provider=None) -> Context:
    db = database.connect(config)
    if config.event_log:
        db.events = EventLog(config.events_path, clock)
    _ensure_demo_backup(config)
    replay = ReplaySource(config.replay_path, clock)
    # Alert source: replay by default; the Wazuh poller only if ALERT_SOURCE=wazuh and Kishaann's class exists.
    live = source
    if live is None and config.alert_source == "wazuh":
        wazuh_source = _optional("ingest.wazuh", "WazuhSource")
        if wazuh_source is None:
            log.warning("ALERT_SOURCE=wazuh but ingest/wazuh.py has no WazuhSource yet; staying on replay")
            db.emit("system.source_fallback", reason="no_wazuh_source", exc_type=None)
        else:
            live = wazuh_source(config, clock)
    # Attack simulation (T8): when SIMULATE is on, the in-app simulator becomes the live
    # source - it *generates* Wazuh-shaped alerts from a script instead of polling a lab.
    # Replay is kept on ctx.replay so the stage fallback buttons still work alongside it.
    sim = None
    if config.simulate and source is None:
        from ingest.simulator import Simulator
        sim = Simulator(config, db, clock)
        live = sim
    # Wazuh client: the fake unless live mode and a real client exists. Simulated actions bypass it anyway.
    client = wazuh_client
    if client is None:
        if config.alert_source == "wazuh":
            try:
                client = _optional("actions.wazuh_client", "RealWazuhClient")(config)
            except Exception as exc:
                # A broken lab config must never take down the demo (T5.09: the lab can be off
                # while the app stays up on the replay fallback). The real client is the only
                # thing that can reach Wazuh; the fake is what a rejected approval would raise
                # wazuh_unavailable against until the lab is fixed.
                log.warning(f"ALERT_SOURCE=wazuh but the Wazuh client is misconfigured "
                            f"({type(exc).__name__}: {exc}); staying on the replay source "
                            f"and the fake client until the lab is fixed.")
                db.emit("system.source_fallback", reason="client_misconfigured", exc_type=type(exc).__name__)
                live, client = None, FakeWazuhClient()
        if client is None:
            client = FakeWazuhClient()
    return Context(
        config=config, db=db, clock=clock,
        source=live or replay, replay=replay, wazuh=client,
        lessons=LessonBook.load(config.lessons_path),
        reword_provider=reword_provider or get_provider(config.ai_provider),
        sim=sim,
    )


async def _timeout_loop(ctx: Context, every: float) -> None:
    while True:
        await asyncio.sleep(every)
        try:
            await asyncio.to_thread(timeout.run_once, ctx.db, ctx.clock, ctx.config, ctx.wazuh)
        except Exception as exc:               # never let one bad pass kill the loop
            log.exception("timeout pass failed")
            ctx.db.emit("system.loop_failed", loop="timeout", exc_type=type(exc).__name__)


HEALTH_KEYS = ("api_ok", "indexer_ok", "agent_active")     # last_alert_at moves on every alert: not a change


async def _ingest_loop(ctx: Context, every: float) -> None:
    """Live mode only: poll the source and push each alert through the pipeline."""
    def cycle() -> None:
        for raw in ctx.source.next_batch():
            try:                                   # one malformed alert must not drop the rest of the batch
                pipeline.process(normalise(raw, now_iso(ctx.clock)), ctx.db, ctx.clock,
                                 lessons=ctx.lessons, config=ctx.config)
            except Exception as exc:
                log.exception("skipped a malformed alert")
                ctx.db.emit("system.loop_failed", loop="ingest_alert", exc_type=type(exc).__name__)
        before = {k: ctx.wazuh_health.get(k) for k in HEALTH_KEYS}
        ctx.wazuh_health.update(ctx.wazuh.health())
        after = {k: ctx.wazuh_health.get(k) for k in HEALTH_KEYS}
        if after != before:
            ctx.db.emit("system.wazuh_health_changed", **after)

    while True:
        await asyncio.sleep(every)
        try:
            await asyncio.to_thread(cycle)
        except Exception as exc:
            log.exception("ingest cycle failed")
            ctx.db.emit("system.loop_failed", loop="ingest", exc_type=type(exc).__name__)


def create_app(config: Config | None = None, clock: Clock | None = None, wazuh_client=None,
               source=None, reword_provider=None, background: bool = True) -> FastAPI:
    """Build the app. Tests pass fakes and ``background=False``."""
    config = config or Config.load()
    ctx = build_context(config, clock or RealClock(), wazuh_client, source, reword_provider)

    # Start-up/shut-down: launch the background loops (timeout every 10 s; Wazuh poll every 5 s in live
    # mode), and cancel them and close the DB on exit.
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks = []
        if background:
            tasks.append(asyncio.create_task(_timeout_loop(ctx, TIMEOUT_TICK_SECONDS)))
            if (config.alert_source == "wazuh" and ctx.source is not ctx.replay) or ctx.sim is not None:
                tasks.append(asyncio.create_task(_ingest_loop(ctx, INGEST_TICK_SECONDS)))
        # Flags only: the config also holds the PIN, tokens and Wazuh passwords.
        ctx.db.emit("system.started", alert_source=config.alert_source, actions=config.actions,
                    ai_reword=config.ai_reword, ai_provider=config.ai_provider,
                    undo_supported=config.undo_supported, event_log_reads=config.event_log_reads)
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            ctx.db.emit("system.stopped")
            ctx.db.close()
            ctx.db.events.close()

    app = FastAPI(title="ShieldMate", lifespan=lifespan)
    app.state.ctx = ctx
    install_handlers(app)
    app.add_middleware(RequestEvents, ctx=ctx)

    # Mount every router under /api. A missing Lane 1 router is a bug (fail loudly); a missing
    # Lane 2 router just means that lane hasn't landed yet (skip it).
    for name in LANE_ONE_ROUTERS + LANE_TWO_ROUTERS:
        router = _optional(f"routes.{name}", "router")
        if router is not None:
            app.include_router(router, prefix="/api")
        elif name in LANE_ONE_ROUTERS:
            raise RuntimeError(f"routes/{name}.py has no router")

    _serve_frontend(app, config)
    return app


def _serve_frontend(app: FastAPI, config: Config) -> None:
    """Serve frontend/dist at / (SPA fallback to index.html) if it has been built."""
    dist = config.frontend_dist
    index = dist / "index.html"
    if not index.is_file():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise ApiError("not_found", "Not found.", 404)
        target = (dist / path).resolve()
        if path and target.is_file() and dist.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(index)        # /staff/*, /owner, /drill/*, /backstage


_app: FastAPI | None = None


def __getattr__(name: str):
    """Lazily build ``main.app`` so ``uvicorn main:app`` works without building it at import time."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
