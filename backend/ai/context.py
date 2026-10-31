"""Build the sanitized context the interpreter agent receives.

The agent only ever sees ids, enums and the app's own short labels (the "task given" text).
It never sees ``log_fields``/``raw`` - those are untrusted (the replay data carries a
prompt-injection string), the same rule as the reword guard (T3.01).
"""
from __future__ import annotations

from db import Database


def build_context(db: Database, *, alert_id: int | None, drill_code: str | None,
                  device_id: int | None, role: str, lang: str) -> dict:
    """The "what I'm looking at" object, ids/labels only. Unknown ids are omitted, not nulled."""
    context: dict = {"role": role, "lang": lang}

    if alert_id is not None:
        row = db.one("SELECT id, rule_id, level, status FROM alerts WHERE id = ?", (alert_id,))
        if row is not None:
            context["alert"] = {"id": row["id"], "rule_id": row["rule_id"],
                                "level": row["level"], "status": row["status"]}

    if drill_code is not None:
        row = db.one("SELECT code, scenario_id, status, step_index FROM drills WHERE code = ?",
                     (drill_code,))
        if row is not None:
            context["drill"] = {"code": row["code"], "scenario_id": row["scenario_id"],
                                "status": row["status"], "step_index": row["step_index"]}

    if device_id is not None:
        row = db.one("SELECT id, agent_name, location FROM devices WHERE id = ?", (device_id,))
        if row is not None:
            context["device"] = {"id": row["id"], "agent_name": row["agent_name"],
                                 "location": row["location"]}

    return context


def fallback_answer(context: dict, question: str) -> str:
    """Plain-language guidance from the labels only - what the route returns when the agent is
    unreachable, so the user still gets something useful instead of an error. Capped for safety."""
    parts = ["The agent isn't reachable right now, so here is the plain version."]
    alert = context.get("alert")
    if alert:
        parts.append(f"You're looking at security alert {alert['id']} "
                     f"(rule {alert['rule_id']}, level {alert['level']}).")
    drill = context.get("drill")
    if drill:
        parts.append(f"You're in drill {drill['code']} (scenario {drill['scenario_id']}).")
    device = context.get("device")
    if device:
        parts.append(f"This is about device {device['agent_name']} in {device['location']}.")
    parts.append("Follow the step shown on your screen and let us know when it's done.")
    answer = " ".join(parts)
    return answer[:2000]
