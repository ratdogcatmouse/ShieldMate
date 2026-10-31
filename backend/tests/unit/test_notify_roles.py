"""v3: who hears about a new attack (alerts/impact.py::notify_roles) and who gets a note (alerts/notify.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from alerts import impact, notify

SEED = Path(__file__).resolve().parents[2] / "seed" / "clinic.json"


@pytest.fixture(scope="module")
def book():
    return impact.ImpactBook.load(SEED)


def test_a_device_notifies_its_account_role_then_the_owner(book):
    assert impact.notify_roles("RECEPTION-PC", book) == ["front_desk", "owner"]
    assert impact.notify_roles("FILE-SERVER", book) == ["billing", "owner"]


def test_the_owners_own_pc_is_not_listed_twice(book):
    assert impact.notify_roles("DOCTOR-PC", book) == ["owner"]


def test_an_unknown_device_or_no_impact_block_falls_back_to_the_owner(book):
    assert impact.notify_roles("NEW-LAPTOP", book) == ["owner"]
    assert impact.notify_roles("RECEPTION-PC", None) == ["owner"]


def test_a_role_without_a_card_is_skipped(make_app, book):
    h = make_app(actions=True)
    h.reset()
    db = h.ctx.db
    # The ransomware card is owner-only: headline_for gives None for the billing role.
    headlines = {"owner": "Files on FILE-SERVER are being locked."}
    ids = notify.attack(db, "2026-11-01T04:00:00Z", alert_id=None, agent_name="FILE-SERVER", action_row_id=None,
                        headline_for=headlines.get, book=book)
    assert len(ids) == 1
    row = db.one("SELECT to_role, kind, text FROM notifications WHERE id = ?", (ids[0],))
    assert (row["to_role"], row["kind"]) == ("owner", "attack")
