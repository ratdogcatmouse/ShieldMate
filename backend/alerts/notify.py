"""Attack notifications: a new alert card tells the people it concerns (v3).

``pipeline.process`` calls ``attack`` once, from its ``created`` branch, so a grouped repeat or a
reopened card never notifies again. The notification points at the alert's BLOCK_IP proposal
(``action_row_id``); ``routes/notifications.py`` turns that into the ``quick_action`` button.
"""
from __future__ import annotations

from typing import Callable

from alerts import impact
from db import Database


def attack(db: Database, now_text: str, *, alert_id: int, agent_name: str, action_row_id: int | None,
           headline_for: Callable[[str], str | None], book: impact.ImpactBook | None) -> list[int]:
    """One ``attack`` notification per relevant role; returns the new notification ids.

    ``headline_for(role)`` is the role's card headline, or None when the lesson has no card for
    that role (the ransomware card is owner-only): that role is skipped, so staff are never told
    about a card they cannot open. It is injected by the pipeline so this module never imports
    it. The text is the filled headline, never ``log_fields`` (those are untrusted log text).
    Runs inside the caller's transaction.
    """
    ids = []
    for role in impact.notify_roles(agent_name, book):
        headline = headline_for(role)
        if headline is None:
            continue
        ids.append(db.add_notification(headline, now_text, alert_id=alert_id, action_row_id=action_row_id,
                                       to_role=role, kind="attack"))
    return ids
