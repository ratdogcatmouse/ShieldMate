"""Replay source: serves replay/alerts.json one "click" at a time.

Each record carries ``replay.type`` (password_guessing | ransomware) and ``replay.click``
(1, 2, ... with no gaps). A Backstage button press injects every record of a type's next
click. The cursor lives in memory, so ``reset_state()`` (called by /demo/reset) rewinds it.
"""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

from clock import Clock, now_iso
from ingest.source import RawAlert


class ReplayExhausted(Exception):
    """No clicks left for that replay type; press Reset."""


class ReplayFileError(ValueError):
    """The replay file breaks the T0.05 rules."""


class ReplaySource:
    def __init__(self, path: Path, clock: Clock):
        self._clock = clock
        self._lock = threading.Lock()
        # type -> click number -> records
        self._clicks: dict[str, dict[int, list[dict]]] = {}
        self._done: dict[str, int] = {}
        self._load(path)

    def _load(self, path: Path) -> None:
        """Read the file and enforce the T0.05 rules: valid type/click, required alert fields, no click gaps."""
        records =json.loads(Path(path).read_text(encoding="utf-8"))
        for rec in records:
            meta = rec.get("replay") or {}
            kind, click = meta.get("type"), meta.get("click")
            alert = rec.get("alert") or {}
            if kind not in ("password_guessing", "ransomware") or not isinstance(click, int):
                raise ReplayFileError(f"bad replay metadata: {meta}")
            if not (alert.get("rule", {}).get("id") and "level" in alert.get("rule", {})
                    and alert.get("agent", {}).get("name")):
                raise ReplayFileError("each record needs rule.id, rule.level and agent.name")
            self._clicks.setdefault(kind, {}).setdefault(click, []).append(alert)
        for kind, clicks in self._clicks.items():
            if sorted(clicks) != list(range(1, len(clicks) + 1)):
                raise ReplayFileError(f"{kind}: click numbers must be 1, 2, ... with no gaps")
        self._done = {kind: 0 for kind in self._clicks}

    @property
    def types(self) -> list[str]:
        return list(self._clicks)

    def clicks_left(self, alert_type: str) -> int:
        with self._lock:
            return len(self._clicks[alert_type]) - self._done[alert_type]

    def next_click(self, alert_type: str) -> tuple[int, list[RawAlert]]:
        """Return (click number, records) and advance the cursor. Raises ReplayExhausted."""
        with self._lock:
            clicks = self._clicks[alert_type]
            click = self._done[alert_type] + 1
            if click > len(clicks):
                raise ReplayExhausted(alert_type)
            self._done[alert_type] = click
            # Copy each record (never mutate the loaded data), stamp it with "now", and wrap it as a RawAlert.
            stamp = now_iso(self._clock)
            batch: list[RawAlert] = []
            for alert in clicks[click]:
                alert = copy.deepcopy(alert)
                alert["timestamp"] = stamp           # "stamping timestamp with now"
                batch.append({
                    "source": "replay",
                    "external_id": None,
                    "alert": alert,
                    "shieldmate": alert.get("shieldmate"),
                })
            return click, batch

    def next_batch(self, alert_type: str | None = None) -> list[RawAlert]:
        if alert_type is None:
            raise ValueError("replay needs an alert type")
        return self.next_click(alert_type)[1]

    def reset_state(self) -> None:
        with self._lock:
            self._done = {kind: 0 for kind in self._clicks}
