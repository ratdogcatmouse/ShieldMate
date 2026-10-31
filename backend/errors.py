"""One error shape for the whole API: ``{"error": "<code>", "message": "<text>"}``.

Codes are exactly ``contract.ErrorCode``. FastAPI's default 422 body is replaced by
``invalid_request`` / 400, and anything unexpected becomes ``internal_error`` / 500 with
a generic message (the details go to the server log only).
"""
from __future__ import annotations

import logging
from typing import get_args

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from contract import ErrorCode

log = logging.getLogger("shieldmate")

ERROR_CODES = set(get_args(ErrorCode))


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        assert code in ERROR_CODES, f"unknown error code {code!r}"
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _body(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


def install_handlers(app: FastAPI) -> None:
    """Register one handler per failure kind so every error leaves as {"error", "message"}."""
    # Our own deliberate errors.
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return _body(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # The spec's 422 override: bad body or query is invalid_request / 400.
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p not in ("body", "query"))
        message = "The request was not valid" + (f" ({where}: {first.get('msg')})." if where else ".")
        return _body("invalid_request", message, 400)

    @app.exception_handler(OverflowError)
    async def _too_big(_: Request, exc: OverflowError):
        # An id too large for SQLite's 64-bit integer (e.g. /alerts/99999999999999999999/done): the
        # caller's mistake, not a server fault.
        return _body("invalid_request", "That number is too large.", 400)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _body("not_found", "Not found.", 404)
        return _body("invalid_request", "The request was not valid.", exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return _body("internal_error", "Something went wrong on the server.", 500)


# --- dependencies shared by the route files ---------------------------------------

def require_flag(name: str):
    """Dependency factory: the route 404s with ``not_enabled`` while the flag is off (T3.05, T4.13)."""
    def dep(request: Request) -> None:
        if not request.app.state.ctx.config.flag(name):
            raise ApiError("not_enabled", "This feature is switched off.", 404)
    return dep


def require_owner(request: Request) -> None:
    """Owner-only routes: needs ``X-Owner-Pin`` once OWNER_PIN is set (decision 3: off for now)."""
    pin = request.app.state.ctx.config.owner_pin
    if not pin:
        return
    given = request.headers.get("X-Owner-Pin")
    if not given:
        raise ApiError("pin_required", "Enter the owner PIN.", 401)
    if given != pin:
        raise ApiError("pin_invalid", "That PIN is not right.", 403)


def require_backstage(request: Request) -> None:
    """``/demo/*``: needs ``X-Backstage-Token`` once BACKSTAGE_TOKEN is set."""
    token = request.app.state.ctx.config.backstage_token
    if not token:
        return
    given = request.headers.get("X-Backstage-Token")
    if not given:
        raise ApiError("pin_required", "The backstage token is required.", 401)
    if given != token:
        raise ApiError("pin_invalid", "That backstage token is not right.", 403)
