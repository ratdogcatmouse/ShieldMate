"""Frontend events from ``POST /api/events``: already checked by the contract, trimmed here.

The phone is untrusted like every other caller: its data keys are cut down to the
type's catalogue keys (and strings to 200 characters) before anything is stored.
"""
from __future__ import annotations

from contract import ClientEvent
from db import Database
from eventlog import catalogue


def ingest(db: Database, session: str, events: list[ClientEvent]) -> int:
    """Store one batch as ``origin='client'`` events, stamped with server time. Returns how many."""
    for ev in events:
        # Cleaned before the ** below: catalogue keys never collide with emit's own keywords.
        data = catalogue.clean(ev.type, {**ev.data, "path": ev.path, "client_ts": ev.client_ts}, strict=False)
        db.emit(ev.type, actor=ev.staff_id, origin="client", session=session, **data)
    return len(events)
