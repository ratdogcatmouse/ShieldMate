"""Grouping: the same rule on the same PC within 10 minutes updates the existing card."""
from __future__ import annotations

from datetime import datetime, timedelta
from sqlite3 import Row

from alerts.normalise import NormalisedAlert
from clock import iso
from db import Database

GROUP_WINDOW = timedelta(minutes=10)
MINE_WINDOW = timedelta(hours=1)        # v2: "That was me" pauses an alert for this long


def find_group(db: Database, alert: NormalisedAlert, now: datetime) -> Row | None:
    """The open card (status ``new``, not closed) for this rule+agent last seen within 10 minutes, if any."""
    cutoff = iso(now - GROUP_WINDOW)
    return db.one(
        "SELECT * FROM alerts WHERE group_key = ? AND status = 'new' AND closed_at IS NULL"
        " AND last_seen >= ? ORDER BY last_seen DESC, id DESC LIMIT 1",
        (alert.group_key, cutoff))


def find_paused(db: Database, alert: NormalisedAlert, now: datetime) -> Row | None:
    """v2: the card someone said "That was me" about within the last hour, for this rule+agent.

    A repeat inside that hour means it wasn't just their typing, so the card comes back.
    """
    cutoff = iso(now - MINE_WINDOW)
    return db.one(
        "SELECT * FROM alerts WHERE group_key = ? AND status = 'mine' AND closed_at IS NULL"
        " AND mine_at >= ? ORDER BY mine_at DESC, id DESC LIMIT 1",
        (alert.group_key, cutoff))


def next_count(existing: int, alert: NormalisedAlert) -> int:
    """New count for a grouped alert.

    Appendix B: a second 60204 that reports 12 failures takes the card from "8+" to "12+".
    An alert with no explicit count (live mode, decision 18) just bumps by one.
    """
    explicit = alert.counts.get("count")
    return explicit if explicit is not None and explicit > existing else existing + 1
