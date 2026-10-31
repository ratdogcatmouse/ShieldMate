"""The only place that reads the time. Everything else takes a ``Clock``.

Tests use ``FakeClock`` and ``advance()`` so the 5-minute approval wait and the 1-hour
block expiry run in milliseconds.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware UTC."""
        ...


class RealClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock:
    """A clock that only moves when told to. Starts at the fixtures' time."""

    def __init__(self, start: str = "2026-11-01T04:00:00Z"):
        self._now = parse_iso(start)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


class OffsetClock:
    """v2: another clock plus an offset Backstage can move forward ("Skip 5 min").

    ``create_app`` wraps every clock in one, so the standing rule's 5-minute wait can be
    shown on stage without waiting. Reset puts the offset back to zero.
    """

    def __init__(self, base: Clock):
        self.base = base
        self.offset = timedelta(0)

    def now(self) -> datetime:
        return self.base.now() + self.offset

    def skip(self, minutes: int) -> None:
        self.offset += timedelta(minutes=minutes)

    def reset(self) -> None:
        self.offset = timedelta(0)

    @property
    def offset_minutes(self) -> int:
        return int(self.offset.total_seconds() // 60)


def iso(dt: datetime) -> str:
    """ISO 8601 UTC with a trailing Z and no fractional seconds: ``2026-11-01T04:10:00Z``."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    """Inverse of ``iso`` (also accepts ``+00:00`` and fractional seconds)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def now_iso(clock: Clock) -> str:
    return iso(clock.now())
