"""ingest -> normalise -> filter -> group -> store. The only module that writes ``alerts``.

Also holds the alert reads the routes need (card assembly per role and language) and
``mark_done``, so the routes never touch SQL.
"""
from __future__ import annotations

import json
from sqlite3 import Row
from typing import Literal

from actions import propose
from alerts import impact
from alerts.filter import should_filter
from alerts.group import find_group, next_count
from alerts.normalise import NormalisedAlert
from clock import Clock, now_iso
from config import Config
from db import Database, mark_device
from errors import ApiError
from lessons.engine import LessonBook

Outcome = Literal["created", "grouped", "filtered", "duplicate"]


def process(alert: NormalisedAlert, db: Database, clock: Clock, *, lessons: LessonBook,
            config: Config) -> Outcome:
    """Store one alert. ``duplicate`` (live mode only) means this indexer ``_id`` was already handled."""
    now = clock.now()
    now_text = now_iso(clock)
    lesson = lessons.get(alert.rule_id)
    raw_text = json.dumps(alert.raw)
    logs_text = json.dumps(alert.log_fields)

    # Everything below is one transaction, so a half-stored alert can never be seen.
    with db.transaction():
        # Step 0: live polling can return the same indexer _id twice; ignore repeats.
        if alert.external_id and db.one("SELECT 1 FROM alerts WHERE external_id = ?", (alert.external_id,)):
            return "duplicate"

        # Step 1: filter. Noise is stored (not dropped) so "N routine events hidden" can be counted.
        if should_filter(alert, lesson):
            # Kept (status 'filtered') so the screen can say "N routine events hidden".
            alert_id = db.execute(
                "INSERT INTO alerts (source, external_id, rule_id, level, agent_name, group_key, count,"
                " lesson_id, status, log_fields, raw, first_seen, last_seen)"
                " VALUES (?,?,?,?,?,?,1,?, 'filtered', ?,?,?,?)",
                (alert.source, alert.external_id, alert.rule_id, alert.level, alert.agent_name,
                 alert.group_key, lesson["lesson_id"] if lesson else None, logs_text, raw_text,
                 now_text, now_text))
            db.emit("alert.filtered", subject=("alert", alert_id), rule_id=alert.rule_id, level=alert.level,
                    agent_name=alert.agent_name, source=alert.source,
                    reason="no_lesson" if lesson is None else "low_level")
            return "filtered"

        # Step 2: group. Same rule+PC within 10 min updates the open card instead of making a new one.
        existing = find_group(db, alert, now)
        if existing is not None:
            count = next_count(existing["count"], alert)
            db.execute(
                "UPDATE alerts SET count = ?, last_seen = ?, raw = ?, log_fields = ? WHERE id = ?",
                (count, now_text, raw_text, logs_text, existing["id"]))
            db.emit("alert.grouped", subject=("alert", existing["id"]), rule_id=alert.rule_id,
                    agent_name=alert.agent_name, source=alert.source, count=count)
            return "grouped"

        # Step 3: store a brand-new card.
        # Decision 18: the first card uses the rule's own definition (e.g. 8 failures in 4 min).
        count = alert.counts.get("count", lesson.get("count_defaults", {}).get("count", 1))
        alert_id = db.execute(
            "INSERT INTO alerts (source, external_id, rule_id, level, agent_name, group_key, count,"
            " lesson_id, status, log_fields, raw, first_seen, last_seen)"
            " VALUES (?,?,?,?,?,?,?,?, 'new', ?,?,?,?)",
            (alert.source, alert.external_id, alert.rule_id, alert.level, alert.agent_name,
             alert.group_key, count, lesson["lesson_id"], logs_text, raw_text, now_text, now_text))
        db.emit("alert.created", subject=("alert", alert_id), rule_id=alert.rule_id, level=alert.level,
                agent_name=alert.agent_name, source=alert.source, lesson_id=lesson["lesson_id"], count=count)

        # Step 4a: with ACTIONS on, a lesson that proposes BLOCK_IP creates an approval request.
        #          (Ransomware's lesson has proposed_action null, so it proposes nothing.)
        if config.actions and lesson.get("proposed_action") == "BLOCK_IP":
            propose.propose(db, clock, alert_id, alert.source, alert.agent_name,
                            alert.log_fields.get("source_ip"))
        # Step 4b: a new password-guessing alert flips that PC's strip to "under attack"
        #          (via Lane 2's set_device_status; a no-op until it exists).
        if alert.rule_id == "60204":
            mark_device(db, alert.agent_name, "under_attack", now_text)
        return "created"


# --- reads --------------------------------------------------------------------
# Read helpers used by routes/alerts.py so the routes never run SQL themselves.

def _values(lessons: LessonBook, lesson: dict, row: Row) -> dict:
    raw_counts = (json.loads(row["raw"]).get("shieldmate") or {})
    extra = {k: raw_counts[k] for k in ("window_minutes", "files_renamed") if k in raw_counts}
    return lessons.values_for(lesson, row["agent_name"], row["count"], extra)


def card(lessons: LessonBook, row: Row, role: str, lang: str) -> dict | None:
    lesson = lessons.get(row["rule_id"])
    if lesson is None:
        return None
    return lessons.card_for(lesson, role, lang, _values(lessons, lesson, row), json.loads(row["log_fields"]))


def alert_out(db: Database, lessons: LessonBook, row: Row, role: str, lang: str,
              book: "impact.ImpactBook | None" = None) -> dict | None:
    """The ``AlertOut`` shape for one role, or None if the lesson has no text for that role.

    With an impact book (routes pass it in) each alert also carries its ``impact``
    (T7.03): what's at risk on this device, so the queue can show what to rush first.
    """
    c = card(lessons, row, role, lang)
    if c is None:
        return None
    lesson = lessons.get(row["rule_id"])
    act = db.one("SELECT id, status, simulated FROM actions WHERE alert_id = ? ORDER BY id DESC LIMIT 1",
                 (row["id"],))
    device = db.device(row["agent_name"])           # JSON-decoded: the impact book reads services as a list
    return {
        "id": row["id"],
        "source": row["source"],
        "rule_id": row["rule_id"],
        "level": row["level"],
        "agent_name": row["agent_name"],
        "lesson_id": row["lesson_id"],
        "severity": lesson["severity"],
        "status": row["status"],
        "count": row["count"],
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "done_by": row["done_by"],
        "card": c,
        "action": None if act is None else {"id": act["id"], "status": act["status"],
                                            "simulated": bool(act["simulated"])},
        "impact": impact.alert_out(book, device, row["rule_id"], row["status"]),
    }


def list_alerts(db: Database, lessons: LessonBook, role: str, lang: str,
                book: "impact.ImpactBook | None" = None, sort: str = "time") -> dict:
    """Every non-filtered alert, plus the hidden-event count.

    ``sort`` (T7.05): "time" is newest ``last_seen`` first (the default, unchanged);
    "impact" leads with the highest impact score so the most dangerous card is on top.
    """
    alerts = []
    rows = db.query("SELECT * FROM alerts WHERE status != 'filtered' ORDER BY last_seen DESC, id DESC")
    for r in rows:
        a = alert_out(db, lessons, r, role, lang, book=book)
        if a is not None:
            alerts.append(a)
    if sort == "impact":
        # Highest score first; no-impact (None) cards sink to the bottom. Stable within
        # a score, so equal cards keep their newest-first order.
        alerts.sort(key=lambda a: -((a["impact"] or {}).get("score", 0)))
    hidden = db.one("SELECT count(*) AS n FROM alerts WHERE status = 'filtered'")["n"]
    return {"hidden_count": hidden, "alerts": alerts}


def mark_done(db: Database, clock: Clock, lessons: LessonBook, alert_id: int, staff_id: int,
              lang: str = "en", book: "impact.ImpactBook | None" = None) -> dict:
    """Staff tapped Done. Idempotent: a second tap changes nothing and sends no second notification."""
    staff = db.staff(staff_id)
    if staff is None:
        raise ApiError("invalid_request", "Unknown staff member.", 400)
    row = db.one("SELECT * FROM alerts WHERE id = ? AND status != 'filtered'", (alert_id,))
    if row is None:
        raise ApiError("not_found", "No such alert.", 404)

    done_event = dict(actor=staff_id, subject=("alert", alert_id), rule_id=row["rule_id"], lang=lang)
    if row["status"] == "done":
        # A repeat tap changes nothing, but repeat taps are worth seeing in the analysis.
        db.emit("alert.done", **done_event, already_done=True)
    else:
        now_text = now_iso(clock)
        c = card(lessons, row, staff["role"], lang) or card(lessons, row, "owner", lang)
        headline = c["headline"] if c else f"alert {alert_id}"
        # A high/critical alert is marked in the owner notification (roadmap 2.3).
        device = db.device(row["agent_name"])
        prefix = impact.notification_prefix(impact.alert_out(book, device, row["rule_id"], row["status"]))
        with db.transaction():
            db.execute("UPDATE alerts SET status='done', done_by=? WHERE id=?", (staff_id, alert_id))
            db.emit("alert.done", **done_event, already_done=False)
            db.add_notification(f"{prefix}{staff['name']} handled: {headline}", now_text,
                                alert_id=alert_id, from_staff_id=staff_id, to_role="owner")
            # Password-guessing device goes back to OK unless a block is protecting it (T4.10).
            if row["rule_id"] == "60204" and propose.active_block(db, row["agent_name"], now_text) is None:
                mark_device(db, row["agent_name"], "ok", now_text)
        row = db.one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    out = alert_out(db, lessons, row, staff["role"], lang, book=book)
    if out is None:        # this role has no card for the alert; fall back to the owner's wording
        out = alert_out(db, lessons, row, "owner", lang, book=book)
    return out
