"""The AI guard (T3.01-T3.03).

The provider is called with exactly two strings, the already-filled headline and why-text.
Log text (usernames, IPs) is never passed in, so the poisoned username can't reach a model.
Its output is used only if it passes every check; otherwise the lesson's pre-written
fallback wording is returned with ``source: "fallback"``.
"""
from __future__ import annotations

import logging
import re

from lessons.engine import fill
from lessons.providers import RewordProvider

MAX_LEN = 200
_DIGITS = re.compile(r"\d+")
_LINK = re.compile(r"https?://|www\.|://|\b[\w-]+\.(?:com|org|net|in|io|co|app|dev|xyz)\b", re.I)

log = logging.getLogger("shieldmate")


def output_ok(original: tuple[str, str], candidate: tuple[str, str]) -> bool:
    """True if ``candidate`` keeps every number, adds none, has no link and fits 200 chars."""
    for old, new in zip(original, candidate):
        # Check 1: a real, non-empty string within the length cap.
        if not isinstance(new, str) or not new.strip() or len(new) > MAX_LEN:
            return False
        # Check 2: no links or bare domains.
        if _LINK.search(new):
            return False
        # Check 3: the set of numbers must be identical (none changed, none added, none dropped).
        if set(_DIGITS.findall(old)) != set(_DIGITS.findall(new)):   # changed number or new digits
            return False
    return True


def reword(provider: RewordProvider, headline: str, why: str, lesson: dict, values: dict) -> dict:
    """Return ``{"headline", "why", "source"}``; ``source`` is ``ai`` only if the guard passed."""
    fallback = {
        "headline": fill(lesson["fallback_reword"]["headline"], values),
        "why": fill(lesson["fallback_reword"]["why"], values),
        "source": "fallback",
    }
    # Ask the provider (two strings only). Any failure, including "not configured", means fallback.
    try:
        new_headline, new_why = provider.reword(headline, why)
    except Exception as exc:     # NotConfigured, timeouts, anything a provider can throw
        log.info("reword fell back: %s", type(exc).__name__)
        return fallback
    # Only trust the answer if it passes the guard.
    if not output_ok((headline, why), (new_headline, new_why)):
        return fallback
    return {"headline": new_headline, "why": new_why, "source": "ai"}
