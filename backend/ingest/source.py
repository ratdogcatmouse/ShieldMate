"""The alert-source seam: replay (demo) and Wazuh (live) both yield ``RawAlert``s."""
from __future__ import annotations

from typing import Literal, Protocol, TypedDict


class RawAlert(TypedDict):
    source: Literal["replay", "wazuh"]
    external_id: str | None      # indexer _id; None for replay
    alert: dict                  # Wazuh alert JSON, same shape as the replay file
    shieldmate: dict | None      # counts block (failures, window_minutes, files_renamed); live may leave None


class AlertSource(Protocol):
    def next_batch(self, alert_type: str | None = None) -> list[RawAlert]:
        """Replay: the records for the next click of ``alert_type`` (called by /demo/replay).
        Wazuh: new alerts since the last poll (called every 5 s by the ingest task)."""
        ...
