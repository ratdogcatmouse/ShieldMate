"""Reword providers. ``AI_PROVIDER=none`` (the default) always falls back to pre-written wording."""
from __future__ import annotations

from typing import Protocol


class NotConfigured(Exception):
    """No AI provider is set up; the guard returns the fallback wording."""


class RewordProvider(Protocol):
    def reword(self, headline: str, why: str) -> tuple[str, str]:
        """Return a rewritten (headline, why). Receives these two strings and nothing else (T3.01)."""
        ...


class NoneProvider:
    def reword(self, headline: str, why: str) -> tuple[str, str]:
        raise NotConfigured("AI_PROVIDER is none")


def get_provider(name: str) -> RewordProvider:
    """Only ``none`` ships today; an unknown name is treated the same (safe default)."""
    return NoneProvider()
