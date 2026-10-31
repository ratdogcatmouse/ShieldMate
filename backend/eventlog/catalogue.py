"""Every event type the log accepts, with the data keys it may carry.

This is the reference for anyone analysing the log later. Payloads hold ids, enums,
counts and durations only: never log text (``log_fields``/``raw`` are untrusted and the
replay data has a prompt-injection string), notification text, reword output, names,
PINs, tokens or Wazuh responses.

Server code that passes an unlisted key is a bug (``db.emit`` asserts); client events
(``ui.*``, from ``POST /api/events``) have unlisted keys dropped instead.
"""
from __future__ import annotations

from typing import NamedTuple

MAX_STRING = 200          # longer strings are cut, whatever their origin
MAX_CLIENT_KEYS = 10


class EventType(NamedTuple):
    keys: tuple[str, ...]
    doc: str


# Keys every client event may carry (ClientEvent.path and client_ts land in data).
CLIENT_COMMON = ("path", "client_ts")

EVENT_TYPES: dict[str, EventType] = {
    # --- alerts (alerts/pipeline.py, routes/alerts.py) ---
    "alert.created": EventType(("rule_id", "level", "agent_name", "source", "lesson_id", "count"),
                               "A new card was stored."),
    "alert.grouped": EventType(("rule_id", "agent_name", "source", "count"),
                               "A repeat within 10 minutes raised an open card's count."),
    "alert.filtered": EventType(("rule_id", "level", "agent_name", "source", "reason"),
                                "Noise kept only for hidden_count; reason is low_level or no_lesson."),
    "alert.done": EventType(("rule_id", "lang", "already_done"), "Staff tapped Done."),
    "alert.reworded": EventType(("role", "lang", "source"), "AI reword asked for; source is ai or fallback."),
    # --- actions (actions/propose.py, actions/timeout.py) ---
    "action.proposed": EventType(("alert_id", "agent_name", "simulated"), "A BLOCK_IP approval request."),
    "action.refused": EventType(("alert_id", "stage", "reason"),
                                "The target failed the safety check; stage is propose or execute."),
    "action.executed": EventType(("alert_id", "via", "simulated", "expires_at"),
                                 "Blocked (or recorded, if simulated); via is tap or standing_rule."),
    "action.failed": EventType(("alert_id", "via", "simulated", "error"), "Wazuh didn't answer; nothing blocked."),
    "action.declined": EventType(("alert_id",), "The owner declined the block."),
    "action.undone": EventType(("alert_id", "simulated"), "An executed block was undone."),
    "action.escalated": EventType(("alert_id", "to_staff_id", "waited_s"),
                                  "Nobody answered in time; the backup approver was asked."),
    "action.expired": EventType(("alert_id", "agent_name"), "A block's time ran out."),
    # --- clinic, notifications, devices ---
    "clinic.standing_rule_set": EventType(("enabled",), "The owner switched the standing rule."),
    "notification.sent": EventType(("alert_id", "action_row_id", "to_role", "to_staff_id"),
                                   "A notification was stored (its text is never logged)."),
    "device.status_changed": EventType(("from_status", "to_status"), "A device strip status moved."),
    # --- drills (drills/engine.py) ---
    "drill.created": EventType(("scenario_id", "source_alert_id", "player_id"), "The host opened a drill lobby."),
    "drill.joined": EventType(("player_id", "rejoin"), "A player joined (rejoin: same player again)."),
    "drill.answered": EventType(("player_id", "step_id", "option_id", "correct", "latency_ms"),
                                "A player locked an answer; latency_ms counts from the step opening."),
    "drill.advanced": EventType(("from_status", "to_status", "step_index", "missed", "auto"),
                                "The drill moved on (auto: closed itself when everyone answered)."),
    # --- restore check (restore/checker.py) ---
    "restore.run": EventType(("result", "files_ok", "files_total", "backup_age_hours", "exposed", "failed_checks"),
                             "A restore check ran."),
    # --- demo (routes/demo.py, db.reset) ---
    "demo.replay": EventType(("alert_type", "click", "injected", "cards_created", "grouped", "filtered"),
                             "Backstage replayed one click of alerts."),
    "demo.reset": EventType(("epoch",), "Back to the seeded clinic; epoch is the new reset count."),
    # --- requests, errors, the process (eventlog/middleware.py, main.py) ---
    "request.completed": EventType(("method", "route", "status", "error", "duration_ms"),
                                   "An /api call finished (successful reads only with EVENT_LOG_READS)."),
    "error.unhandled": EventType(("method", "route", "exc_type"), "A request crashed with a 500."),
    "system.started": EventType(("alert_source", "actions", "ai_reword", "ai_provider", "undo_supported",
                                 "event_log_reads"), "The server started (flags only, never secrets)."),
    "system.stopped": EventType((), "The server shut down cleanly."),
    "system.source_fallback": EventType(("reason", "exc_type"), "Live mode fell back to replay at start-up."),
    "system.loop_failed": EventType(("loop", "exc_type"), "One background pass failed; the loop carries on."),
    "system.wazuh_health_changed": EventType(("api_ok", "indexer_ok", "agent_active"),
                                             "The live Wazuh health snapshot changed."),
    # --- the frontend (POST /api/events; contract.ClientEventType lists the same names) ---
    "ui.page_view": EventType(CLIENT_COMMON, "A screen was shown."),
    "ui.person_picked": EventType(CLIENT_COMMON + ("role",), "Someone picked who uses this device."),
    "ui.lang_changed": EventType(CLIENT_COMMON + ("lang", "from_lang"), "The card language was switched."),
    "ui.log_details_opened": EventType(CLIENT_COMMON + ("alert_id",), "\"Details from the log\" was opened."),
    "ui.call_it_tapped": EventType(CLIENT_COMMON + ("alert_id",), "The Call IT button was tapped."),
    "ui.drill_join_submitted": EventType(CLIENT_COMMON + ("code",), "The join-a-drill form was sent."),
    "ui.reset_armed": EventType(CLIENT_COMMON, "Backstage Reset was tapped once (waiting for the second tap)."),
    "ui.api_error": EventType(CLIENT_COMMON + ("method", "route", "status", "error"), "An API call failed on the phone."),
    "ui.app_error": EventType(CLIENT_COMMON + ("message", "source"), "A script error on the phone."),
}


def _cut(value):
    return value[:MAX_STRING] if isinstance(value, str) else value


def clean(type_: str, data: dict, *, strict: bool) -> dict:
    """Keep only the type's keys and cut long strings. ``strict`` (server code) asserts instead of dropping."""
    assert type_ in EVENT_TYPES, f"unknown event type {type_!r}"
    allowed = EVENT_TYPES[type_].keys
    if strict:
        extra = set(data) - set(allowed)
        assert not extra, f"{type_} does not allow {sorted(extra)}"
    kept = {k: _cut(v) for k, v in data.items() if k in allowed}
    if not strict:
        kept = dict(list(kept.items())[:MAX_CLIENT_KEYS])
    return kept
