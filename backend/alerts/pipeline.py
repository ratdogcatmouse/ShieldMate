"""ingest -> normalise -> filter -> group -> store. The only module that writes ``alerts``
(except the IT-loop columns, which belong to ``alerts/it.py``).

Also holds the alert reads the routes need (card assembly per role and language) and the
staff actions on a card - ``mark_done``, and in v2 ``set_step``, ``say_mine`` and
``reopen`` - so the routes never touch SQL.
"""
from __future__ import annotations

import json
from sqlite3 import Row
from typing import Literal

from actions import propose
from alerts import impact, it, notify
from alerts.filter import should_filter
from alerts.group import find_group, find_paused, next_count
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

        # Step 2a (v2): a repeat within an hour of "That was me" brings that card back.
        paused = find_paused(db, alert, now)
        if paused is not None:
            count = next_count(paused["count"], alert)
            db.execute(
                "UPDATE alerts SET status = 'new', reopened = 1, count = ?, last_seen = ?, raw = ?,"
                " log_fields = ? WHERE id = ?",
                (count, now_text, raw_text, logs_text, paused["id"]))
            db.emit("alert.reopened", subject=("alert", paused["id"]), rule_id=alert.rule_id, trigger="repeat")
            _after_reopen(db, clock, config, lessons, paused["id"], now_text)
            return "grouped"

        # Step 2b: group. Same rule+PC within 10 min updates the open card instead of making a new one.
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
        action_row_id = None
        if config.actions and lesson.get("proposed_action") == "BLOCK_IP":
            action_row_id = propose.propose(db, clock, alert_id, alert.source, alert.agent_name,
                                            alert.log_fields.get("source_ip"))
        # Step 4a2 (v3): tell the people this concerns. Only a brand-new card gets here, so repeats
        #          stay quiet. The notification carries the proposal so the phone can show a Block button.
        new_row = db.one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        notify.attack(db, now_text, alert_id=alert_id, agent_name=alert.agent_name,
                      action_row_id=action_row_id, book=impact.book_for(config.seed_path),
                      headline_for=lambda role: (card(lessons, new_row, role, "en") or {}).get("headline"))
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


def _steps_done(db: Database, alert_id: int) -> dict[str, Row]:
    """v2: the ticked steps of one alert, by action ID."""
    return {r["action"]: r for r in db.query("SELECT * FROM alert_steps WHERE alert_id = ?", (alert_id,))}


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
    # Ticks are stored by action ID, so a step ticked from one role's card shows on every role's card.
    done = _steps_done(db, row["id"])
    c["steps"] = [{**s, "done": s["action"] in done,
                   "done_by": done[s["action"]]["done_by"] if s["action"] in done else None,
                   "done_at": done[s["action"]]["done_at"] if s["action"] in done else None}
                  for s in c["steps"]]
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
        "done_at": row["done_at"],
        "mine_by": row["mine_by"],
        "mine_at": row["mine_at"],
        "reopened": bool(row["reopened"]),
        "can_say_mine": bool(lesson.get("that_was_me")),
        "card": c,
        "action": None if act is None else {"id": act["id"], "status": act["status"],
                                            "simulated": bool(act["simulated"])},
        "it": it.it_out(db, row, done.get("CALL_SAVED_IT")),
        "impact": impact.alert_out(book, device, row["rule_id"], row["status"]),
    }


def alert_out_for(db: Database, lessons: LessonBook, alert_id: int, role: str, lang: str,
                  book: "impact.ImpactBook | None" = None) -> dict:
    """One alert re-read after a write, in ``role``'s wording - or the owner's when that role has no card."""
    row = db.one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    return alert_out(db, lessons, row, role, lang, book=book) or alert_out(db, lessons, row, "owner", lang, book=book)


def list_alerts(db: Database, lessons: LessonBook, role: str, lang: str,
                book: "impact.ImpactBook | None" = None, sort: str = "time",
                include_closed: bool = False) -> dict:
    """Every non-filtered alert, plus the hidden-event count.

    ``sort`` (T7.05): "time" is newest ``last_seen`` first (the default, unchanged);
    "impact" leads with the highest impact score so the most dangerous card is on top.
    Closed incidents (v2: the owner confirmed IT's fix) are left out unless ``include_closed``.
    """
    alerts = []
    rows = db.query("SELECT * FROM alerts WHERE status != 'filtered'"
                    + ("" if include_closed else " AND closed_at IS NULL")
                    + " ORDER BY last_seen DESC, id DESC")
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


# --- staff actions on a card -------------------------------------------------------

def _staff_and_alert(db: Database, alert_id: int, staff_id: int) -> tuple[dict, Row]:
    """The acting staff member and the (non-filtered) alert, or the matching 400/404."""
    staff = db.staff(staff_id)
    if staff is None:
        raise ApiError("invalid_request", "Unknown staff member.", 400)
    row = db.one("SELECT * FROM alerts WHERE id = ? AND status != 'filtered'", (alert_id,))
    if row is None:
        raise ApiError("not_found", "No such alert.", 404)
    return staff, row


def _headline(lessons: LessonBook, row: Row, role: str, lang: str, alert_id: int) -> str:
    c = card(lessons, row, role, lang) or card(lessons, row, "owner", lang)
    return c["headline"] if c else f"alert {alert_id}"


def mark_done(db: Database, clock: Clock, lessons: LessonBook, alert_id: int, staff_id: int,
              lang: str = "en", book: "impact.ImpactBook | None" = None) -> dict:
    """Staff tapped Done. Idempotent: a second tap changes nothing and sends no second notification."""
    staff, row = _staff_and_alert(db, alert_id, staff_id)

    done_event = dict(actor=staff_id, subject=("alert", alert_id), rule_id=row["rule_id"], lang=lang)
    if row["status"] == "done":
        # A repeat tap changes nothing, but repeat taps are worth seeing in the analysis.
        db.emit("alert.done", **done_event, already_done=True)
    else:
        now_text = now_iso(clock)
        headline = _headline(lessons, row, staff["role"], lang, alert_id)
        # A high/critical alert is marked in the owner notification (roadmap 2.3).
        device = db.device(row["agent_name"])
        prefix = impact.notification_prefix(impact.alert_out(book, device, row["rule_id"], row["status"]))
        with db.transaction():
            db.execute("UPDATE alerts SET status='done', done_by=?, done_at=? WHERE id=?",
                       (staff_id, now_text, alert_id))
            db.emit("alert.done", **done_event, already_done=False)
            db.add_notification(f"{prefix}{staff['name']} handled: {headline}", now_text,
                                alert_id=alert_id, from_staff_id=staff_id, to_role="owner")
            # Password-guessing device goes back to OK unless a block is protecting it (T4.10).
            if row["rule_id"] == "60204" and propose.active_block(db, row["agent_name"], now_text) is None:
                mark_device(db, row["agent_name"], "ok", now_text)
    return alert_out_for(db, lessons, alert_id, staff["role"], lang, book=book)


def set_step(db: Database, clock: Clock, lessons: LessonBook, alert_id: int, action: str,
             staff_id: int, done: bool, lang: str = "en", book: "impact.ImpactBook | None" = None) -> dict:
    """v2: tick or untick one step of the card. Idempotent both ways; the first tick keeps its who/when.

    The step must be on this person's own card. Ticking CALL_SAVED_IT for the first time
    also starts the IT loop ("called"), which the IT contact's panel picks up.
    """
    staff, row = _staff_and_alert(db, alert_id, staff_id)
    if row["closed_at"] is not None:
        raise ApiError("already_closed", "This incident is already closed.", 409)
    body = lessons.get(row["rule_id"])["roles"].get(staff["role"]) or {"steps": []}
    if action not in {s["action"] for s in body["steps"]}:
        raise ApiError("invalid_request", "That step isn't on your card.", 400)
    now_text = now_iso(clock)
    with db.transaction():
        if done:
            ticked = db.one("SELECT 1 FROM alert_steps WHERE alert_id = ? AND action = ?", (alert_id, action))
            if not ticked:
                db.execute("INSERT INTO alert_steps (alert_id, action, done_by, done_at) VALUES (?,?,?,?)",
                           (alert_id, action, staff_id, now_text))
                if action == "CALL_SAVED_IT":
                    it.log(db, alert_id, now_text, "called", staff_id)
        else:
            db.execute("DELETE FROM alert_steps WHERE alert_id = ? AND action = ?", (alert_id, action))
        db.emit("alert.step_set", actor=staff_id, subject=("alert", alert_id), rule_id=row["rule_id"],
                step_action=action, done=done)
    return alert_out_for(db, lessons, alert_id, staff["role"], lang, book=book)


def say_mine(db: Database, clock: Clock, lessons: LessonBook, alert_id: int, staff_id: int,
             lang: str = "en", book: "impact.ImpactBook | None" = None) -> dict:
    """v2: "That was me: I mistyped my password". Pauses the alert for an hour.

    Only lessons marked ``that_was_me`` allow it, and only on an open card (a second tap
    changes nothing). A pending block request is withdrawn, the owner is told, and the
    device strip goes back to OK unless a block is protecting it. A repeat of the same
    rule on the same PC within the hour reopens the card (``process``, step 2a).
    """
    staff, row = _staff_and_alert(db, alert_id, staff_id)
    if not lessons.get(row["rule_id"]).get("that_was_me"):
        raise ApiError("invalid_request", "This alert can't be marked as your own mistake.", 400)
    if row["closed_at"] is not None:
        raise ApiError("already_closed", "This incident is already closed.", 409)
    if row["status"] == "mine":
        return alert_out_for(db, lessons, alert_id, staff["role"], lang, book=book)
    if row["status"] != "new":
        raise ApiError("invalid_request", "Only an open alert can be paused.", 400)
    now_text = now_iso(clock)
    with db.transaction():
        db.execute("UPDATE alerts SET status = 'mine', mine_by = ?, mine_at = ? WHERE id = ?",
                   (staff_id, now_text, alert_id))
        db.emit("alert.mine", actor=staff_id, subject=("alert", alert_id), rule_id=row["rule_id"])
        propose.withdraw_pending(db, alert_id, "mine")
        db.add_notification(
            f"{staff['name']} says the alert on {row['agent_name']} was their own mistyping."
            " It comes back if it happens again within an hour.",
            now_text, alert_id=alert_id, from_staff_id=staff_id, to_role="owner")
        if row["rule_id"] == "60204" and propose.active_block(db, row["agent_name"], now_text) is None:
            mark_device(db, row["agent_name"], "ok", now_text)
    return alert_out_for(db, lessons, alert_id, staff["role"], lang, book=book)


def reopen(db: Database, clock: Clock, config: Config, lessons: LessonBook, alert_id: int, staff_id: int,
           lang: str = "en", book: "impact.ImpactBook | None" = None) -> dict:
    """v2: "It wasn't all me": a paused alert goes back to open, exactly as a repeat would reopen it."""
    staff, row = _staff_and_alert(db, alert_id, staff_id)
    if row["status"] != "mine":
        raise ApiError("invalid_request", "Only a paused alert can be reopened.", 400)
    now_text = now_iso(clock)
    with db.transaction():
        db.execute("UPDATE alerts SET status = 'new', reopened = 1 WHERE id = ?", (alert_id,))
        db.emit("alert.reopened", actor=staff_id, subject=("alert", alert_id), rule_id=row["rule_id"],
                trigger="staff")
        _after_reopen(db, clock, config, lessons, alert_id, now_text)
    return alert_out_for(db, lessons, alert_id, staff["role"], lang, book=book)


def _after_reopen(db: Database, clock: Clock, config: Config, lessons: LessonBook, alert_id: int,
                  now_text: str) -> None:
    """A paused alert is open again: tell the owner, mark the PC, and ask again about a block.

    Runs inside the caller's transaction.
    """
    row = db.one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    lesson = lessons.get(row["rule_id"])
    who = db.staff(row["mine_by"]) if row["mine_by"] is not None else None
    db.add_notification(
        f"It happened again after {who['name'] if who else 'staff'} said \"That was me\": "
        f"{_headline(lessons, row, 'owner', 'en', alert_id)}",
        now_text, alert_id=alert_id, to_role="owner")
    if row["rule_id"] == "60204":
        mark_device(db, row["agent_name"], "under_attack", now_text)
    # The earlier request was withdrawn by "That was me"; a reopened attack needs a fresh one
    # (unless one is still pending, or a block is already protecting the PC).
    pending = db.one("SELECT 1 FROM actions WHERE alert_id = ? AND status = 'proposed'", (alert_id,))
    if (config.actions and lesson.get("proposed_action") == "BLOCK_IP" and pending is None
            and propose.active_block(db, row["agent_name"], now_text) is None):
        propose.propose(db, clock, alert_id, row["source"], row["agent_name"],
                        json.loads(row["log_fields"]).get("source_ip"))
