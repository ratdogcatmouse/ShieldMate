"""Lesson engine: rule ID -> role-specific card text (the "translator" for non-technical staff).

``lessons.json`` holds one entry per rule. ``card_for`` fills the placeholders
({agent_name}, {count}, {window_minutes}, {files_renamed}) and picks the role's wording
and, when asked, the Kannada/Hindi translation, falling back to English one string at a time.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

from contract import ActionId, Lang, Role

PLACEHOLDERS = {"agent_name", "count", "window_minutes", "files_renamed"}
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
ROLES = set(get_args(Role))
LANGS = set(get_args(Lang))
ACTION_IDS = set(get_args(ActionId))
SEVERITIES = {"needs_you_now", "heads_up"}


class LessonError(ValueError):
    """lessons.json breaks the T0.06 rules."""


def fill(text: str, values: dict) -> str:
    """Replace known placeholders only; anything else in braces is left alone."""
    return _PLACEHOLDER_RE.sub(
        lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


class LessonBook:
    def __init__(self, lessons: list[dict]):
        self._by_rule: dict[str, dict] = {}
        for lesson in lessons:
            self._validate(lesson)
            if lesson["rule_id"] in self._by_rule:
                raise LessonError(f"duplicate rule_id {lesson['rule_id']}")
            self._by_rule[lesson["rule_id"]] = lesson

    @classmethod
    def load(cls, path: Path) -> "LessonBook":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    # --- validation -----------------------------------------------------------

    @staticmethod
    def _check_text(rule: str, text: str) -> None:
        for name in _PLACEHOLDER_RE.findall(text):
            if name not in PLACEHOLDERS:
                raise LessonError(f"rule {rule}: unknown placeholder {{{name}}}")

    def _validate(self, lesson: dict) -> None:
        rule = lesson.get("rule_id", "?")
        for key in ("rule_id", "lesson_id", "severity", "roles", "fallback_reword"):
            if key not in lesson:
                raise LessonError(f"rule {rule}: missing {key}")
        if lesson["severity"] not in SEVERITIES:
            raise LessonError(f"rule {rule}: bad severity {lesson['severity']}")
        if lesson.get("proposed_action") not in (None, "BLOCK_IP"):
            raise LessonError(f"rule {rule}: bad proposed_action")
        for role, body in lesson["roles"].items():
            if role not in ROLES:
                raise LessonError(f"rule {rule}: unknown role {role}")
            for key in ("headline", "what_we_know", "why"):
                self._check_text(rule, body[key])
            for step in body["steps"]:
                if step["action"] not in ACTION_IDS:
                    raise LessonError(f"rule {rule}: unknown action {step['action']}")
                self._check_text(rule, step["text"])
            for lang, tr in body.get("translations", {}).items():
                if lang not in LANGS:
                    raise LessonError(f"rule {rule}: unknown language {lang}")
                if "steps" in tr and len(tr["steps"]) != len(body["steps"]):
                    raise LessonError(f"rule {rule}/{role}/{lang}: translated steps must match in number")

    # --- lookup ---------------------------------------------------------------

    def get(self, rule_id: str) -> dict | None:
        return self._by_rule.get(rule_id)

    def by_lesson_id(self, lesson_id: str) -> dict | None:
        return next((l for l in self._by_rule.values() if l["lesson_id"] == lesson_id), None)

    @property
    def rule_ids(self) -> list[str]:
        return list(self._by_rule)

    # --- card -----------------------------------------------------------------

    @staticmethod
    def values_for(lesson: dict, agent_name: str, count: int | None, extra: dict | None) -> dict:
        """Placeholder values: the alert's own counts, else the lesson's ``count_defaults``."""
        values = {**lesson.get("count_defaults", {}), **(extra or {})}
        if count is not None:
            values["count"] = count
        values["agent_name"] = agent_name
        return values

    def card_for(self, lesson: dict, role: str, lang: str, values: dict, log_fields: dict) -> dict | None:
        """The card for ``role``/``lang``, or None when the lesson has no text for that role."""
        body = lesson["roles"].get(role)
        if body is None:
            return None
        # Translation for this language, if any; each string falls back to English on its own.
        tr = body.get("translations", {}).get(lang, {}) if lang != "en" else {}
        steps_tr = tr.get("steps") or []
        # Only the log fields this role's lesson allows (front desk sees the username, owner also the IP).
        shown ={k: v for k, v in log_fields.items() if k in body.get("show_log_fields", [])}
        return {
            "lang": lang,
            "headline": fill(tr.get("headline") or body["headline"], values),
            "what_we_know": fill(tr.get("what_we_know") or body["what_we_know"], values),
            "why": fill(tr.get("why") or body["why"], values),
            "steps": [
                # The action ID never changes with the language; only the text does.
                {"action": s["action"],
                 "text": fill((steps_tr[i] if i < len(steps_tr) and steps_tr[i] else s["text"]), values)}
                for i, s in enumerate(body["steps"])
            ],
            "log_fields": shown,
            "drill_scenario": lesson.get("drill_scenario"),
        }
