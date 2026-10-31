"""Noise filter: level below 7, or a rule with no lesson, never becomes a card (T2.01)."""
from __future__ import annotations

from alerts.normalise import NormalisedAlert

MIN_LEVEL = 7


def should_filter(alert: NormalisedAlert, lesson: dict | None) -> bool:
    return alert.level < MIN_LEVEL or lesson is None
