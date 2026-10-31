"""POST /restore/run and GET /restore/latest (T1.12-T1.15, T1.16).

The route bodies are thin: the check itself (sandbox copy, hashes, age, exposure)
lives in ``restore.checker`` so it is unit-testable without HTTP.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from contract import RestoreRun
from errors import require_owner
from restore import checker

router = APIRouter()


@router.post("/restore/run", response_model=RestoreRun, dependencies=[Depends(require_owner)])
def post_run(request: Request):
    """Run the check now and store the result. The backup folder comes only from
    RESTORE_BACKUP_DIR, never from the request (safety rule, T1.12)."""
    ctx = request.app.state.ctx
    return checker.run(ctx.db, ctx.clock, ctx.config)


@router.get("/restore/latest", response_model=RestoreRun)
def get_latest(request: Request):
    """The newest stored run, or the NOT_TESTED placeholder before the first one after a reset."""
    ctx = request.app.state.ctx
    return checker.latest(ctx.db, ctx.config)
