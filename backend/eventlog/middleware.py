"""Per-request event context: a request id, the phone's session id, and ``request.completed``.

A plain ASGI middleware (not ``BaseHTTPMiddleware``), so the context variables it sets
reach the sync route handlers' threads and every ``db.emit`` they make. It sits inside
Starlette's error middleware, so a crash passes through here before becoming a 500.
"""
from __future__ import annotations

import re
import time
import uuid

from eventlog.log import request_id, session_id

SESSION_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
READS = ("GET", "HEAD", "OPTIONS")
# Its own route records client events; logging the request too would double every batch.
SKIP = ("/api/events",)


class RequestEvents:
    def __init__(self, app, ctx):
        self.app = app
        self.ctx = ctx

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/") or path in SKIP:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        sid = headers.get(b"x-session-id", b"").decode("latin-1")
        rid_token = request_id.set(uuid.uuid4().hex[:12])
        sid_token = session_id.set(sid if SESSION_RE.match(sid) else None)
        status = {"code": 500}
        started = time.perf_counter()       # a duration, not a wall-clock time, so not the Clock

        async def send_status(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_status)
        except Exception as exc:
            self._emit(scope, 500, "internal_error", started)
            self.ctx.db.emit("error.unhandled", method=scope["method"], route=_route(scope),
                             exc_type=type(exc).__name__)
            raise
        else:
            error = (scope.get("state") or {}).get("error_code")
            self._emit(scope, status["code"], error, started)
        finally:
            request_id.reset(rid_token)
            session_id.reset(sid_token)

    def _emit(self, scope, status: int, error: str | None, started: float) -> None:
        # Successful reads are the phones' 2 s polls: skipped unless EVENT_LOG_READS is on.
        if scope["method"] in READS and status < 400 and not self.ctx.config.event_log_reads:
            return
        self.ctx.db.emit("request.completed", method=scope["method"], route=_route(scope), status=status,
                         error=error, duration_ms=round((time.perf_counter() - started) * 1000, 1))


def _route(scope) -> str | None:
    """The matched route's template (``/alerts/{alert_id}/done``): never the raw path or query."""
    route = scope.get("route")
    return getattr(route, "path", None)
