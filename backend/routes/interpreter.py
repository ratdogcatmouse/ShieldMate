"""POST /interpreter/chat - ask the n8n agent to explain a task the user is stuck on.

Thin and flag-gated (AI_INTERPRETER): build a sanitized context, proxy the question to the
agent, and return the answer. If the agent is unreachable the user gets a plain-language
fallback instead of an error (a dead n8n must never take the app down, T5.09).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from ai import context as ctxctx
from contract import InterpreterRequest, InterpreterResponse
from errors import require_flag

log = logging.getLogger("shieldmate")

router = APIRouter()


@router.post("/interpreter/chat", response_model=InterpreterResponse,
             dependencies=[Depends(require_flag("AI_INTERPRETER"))])
def post_chat(body: InterpreterRequest, request: Request):
    ctx = request.app.state.ctx
    # The flag is on, so a client must be wired. If it isn't (misconfigured URL swallowed the
    # real one), fall back so the route still answers.
    context = ctxctx.build_context(ctx.db, alert_id=body.alert_id, drill_code=body.drill_code,
                                   device_id=body.device_id, role=body.role, lang=body.lang)
    if ctx.interpreter is None:
        return InterpreterResponse(answer=ctxctx.fallback_answer(context, body.question),
                                   source="fallback")
    try:
        answer = ctx.interpreter.ask(body.question, context, body.role, body.lang)
        source = "ai"
    except Exception as exc:
        # Timeout, TLS failure, a weird answer shape - anything from the real client. Never 500.
        log.info("interpreter fell back: %s", type(exc).__name__)
        answer = ctxctx.fallback_answer(context, body.question)
        source = "fallback"
    # Which way it went and what it was about - ids/enums only, never the question or the answer.
    ctx.db.emit("interpreter.query", alert_id=body.alert_id, drill_code=body.drill_code,
                device_id=body.device_id, role=body.role, lang=body.lang, source=source)
    return InterpreterResponse(answer=answer[:2000], source=source)
