"""POST /restore/run, POST /restore/verify, GET /restore/latest (T1.12-T1.15, T1.16), and the
v3 restore-incident loop (GET /restore/incidents, POST .../resolve, POST .../close).

The route bodies are thin: the check itself (sandbox copy, hashes, age, exposure) lives in
``restore.checker``, the verification in ``restore.verify``, and the incident state machine in
``restore.incident`` - all unit-testable without HTTP.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from contract import (RestoreIncident, RestoreIncidentCloseRequest, RestoreIncidentsResponse,
                      RestoreIncidentResolveRequest, RestoreRun, RestoreVerifyResult)
from errors import require_owner
from restore import checker, incident, verify

router = APIRouter()


@router.post("/restore/run", response_model=RestoreRun, dependencies=[Depends(require_owner)])
def post_run(request: Request):
    """Run the check now and store the result. The backup folder comes only from
    RESTORE_BACKUP_DIR, never from the request (safety rule, T1.12)."""
    ctx = request.app.state.ctx
    return checker.run(ctx.db, ctx.clock, ctx.config)


@router.post("/restore/verify", response_model=RestoreVerifyResult, dependencies=[Depends(require_owner)])
def post_verify(request: Request):
    """The real recovery story: back up the compromised directory, apply the IT patch to a
    sandbox copy of the live directory, then compare the two for the same vulnerabilities.
    Sandbox writes only; the live trees are never touched."""
    ctx = request.app.state.ctx
    return verify.run_verify(ctx.db, ctx.clock, ctx.config)


@router.get("/restore/latest", response_model=RestoreRun)
def get_latest(request: Request):
    """The newest stored *check* run, or the NOT_TESTED placeholder before the first one after a reset."""
    ctx = request.app.state.ctx
    return checker.latest(ctx.db, ctx.config)


# --- v3: the restore-incident loop ---------------------------------------------
# A FAIL check opens an incident (in checker.run). The IT contact polls the list below - that
# is how IT is alerted, the same way the IT panel sees alerts, so no new notification role is
# added. IT resolves it; the owner (after retesting) closes it or sends it back.

@router.get("/restore/incidents", response_model=RestoreIncidentsResponse)
def get_incidents(request: Request):
    """The IT contact's poll: every incident, newest first."""
    ctx = request.app.state.ctx
    return {"incidents": incident.list_all(ctx.db)}


@router.post("/restore/incidents/resolve", response_model=RestoreIncident)
def post_resolve(body: RestoreIncidentResolveRequest, request: Request):
    """The IT contact marks the open incident resolved and says what they did."""
    ctx = request.app.state.ctx
    return incident.resolve(ctx.db, ctx.clock, ctx.config, body.note)


@router.post("/restore/incidents/close", response_model=RestoreIncident, dependencies=[Depends(require_owner)])
def post_close(body: RestoreIncidentCloseRequest, request: Request):
    """The owner closes the incident once IT has resolved it and a retest is safe, or sends it
    back to IT (``confirm=false``) when it still isn't."""
    ctx = request.app.state.ctx
    return incident.close(ctx.db, ctx.clock, body.staff_id, body.confirm, body.note)
