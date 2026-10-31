"""Who an alert concerns, and the attack notifications that tell them (v3).

``audience`` is the one routing rule: the roles that see an alert's card (``pipeline.list_alerts``),
may act on it, and get its attack notification. ``pipeline.process`` calls ``attack`` once, from its
``created`` branch, so a grouped repeat or a reopened card never notifies again. The notification
points at the alert's BLOCK_IP proposal (``action_row_id``); ``routes/notifications.py`` turns that
into the ``quick_action`` button.
"""
from __future__ import annotations

from typing import Callable

from alerts import impact
from db import Database


def audience(lesson: dict, agent_name: str, book: impact.ImpactBook | None) -> list[str]:
    """The roles an alert on ``agent_name`` concerns, owner last.

    Starts from the lesson's ``notify_roles`` when it names them (v4: the doctor's mailbox sending
    fake fee requests concerns the whole team), else the device's own account (``impact.notify_roles``).
    Two rules always hold on top of that:

    - A computer that belongs to one staff role never reaches another staff role: an alert on
      RECEPTION-PC (front desk's) never reaches billing, and one on FILE-SERVER (billing's) never
      reaches the front desk. Only the owner's computer, or one the seed doesn't know, is shared.
    - The owner is always included. The owner's screens and the IT contact's panel (which reads the
      owner's wording) therefore see every alert.

    A role in the list still only gets a card when the lesson has wording for it.
    """
    device_roles = impact.notify_roles(agent_name, book)        # [account, "owner"] or ["owner"]
    owned_by = device_roles[0] if device_roles[0] != "owner" else None
    roles = []
    for role in lesson.get("notify_roles") or device_roles:
        if owned_by is not None and role not in (owned_by, "owner"):
            continue
        if role not in roles:
            roles.append(role)
    if "owner" in roles:
        roles.remove("owner")
    return roles + ["owner"]


def attack(db: Database, now_text: str, *, alert_id: int, agent_name: str, action_row_id: int | None,
           headline_for: Callable[[str], str | None], book: impact.ImpactBook | None,
           roles: list[str] | None = None) -> list[int]:
    """One ``attack`` notification per relevant role; returns the new notification ids.

    ``roles`` is the alert's ``audience`` (the pipeline always passes it); without it the list
    is the device's account, then the owner.

    ``headline_for(role)`` is the role's card headline, or None when the lesson has no card for
    that role (the ransomware card is owner-only): that role is skipped, so staff are never told
    about a card they cannot open. It is injected by the pipeline so this module never imports
    it. The text is the filled headline, never ``log_fields`` (those are untrusted log text).
    Runs inside the caller's transaction.
    """
    ids = []
    for role in roles or impact.notify_roles(agent_name, book):
        headline = headline_for(role)
        if headline is None:
            continue
        ids.append(db.add_notification(headline, now_text, alert_id=alert_id, action_row_id=action_row_id,
                                       to_role=role, kind="attack"))
    return ids
