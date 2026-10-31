"""Live alert source: Wazuh indexer hits -> ``RawAlert``s for the shared pipeline.

``actions/wazuh_client.py`` only talks to Wazuh (``RealWazuhClient.alert_hits``); this module
decides *which* alerts to ask for and hands them to ``alerts.normalise`` / ``alerts.pipeline``
unchanged, exactly like replayed alerts. Nothing here ever blocks an IP: a block only happens
after an approval, in ``actions/``.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable

from actions.wazuh_client import RealWazuhClient, WazuhClient, utc_now
from clock import Clock
from ingest.source import RawAlert

log = logging.getLogger("shieldmate")

LOOKBACK = timedelta(minutes=2)


class WazuhSource:
    """Implements ``AlertSource`` for ALERT_SOURCE=wazuh; ``main`` calls ``next_batch`` every 5 s."""

    def __init__(self, config, clock: Clock, client: WazuhClient | None = None):
        # ``client`` is only for tests; main.py passes (config, clock) and gets the real client.
        self._client = client or RealWazuhClient(config)
        self._clock = clock
        self._lock = threading.Lock()
        # Alerts from before start-up (old demo data) are never ingested.
        self._started_at = clock.now()
        # End of the last poll that fully succeeded; failures leave it alone so the next tick retries.
        self._last_success = self._started_at
        # external_id -> alert timestamp for ids already returned. The 2-minute look-back
        # re-fetches recent alerts, and the pipeline can only dedupe ids it stored on a row;
        # a *grouped* alert only bumps a count, so without this it would be counted again.
        self._seen: dict[str, datetime] = {}

    def next_batch(self, alert_type: str | None = None) -> list[RawAlert]:
        with self._lock:
            end = self._clock.now()
            start = max(self._started_at, self._last_success - LOOKBACK)
            # Consume the whole scroll before touching any state: an error raises from here and
            # leaves the cursor (and the seen map) as they were.
            hits = list(self._client.alert_hits(start, end))

            batch: list[RawAlert] = []
            for hit in hits:
                try:
                    external_id = f"{hit['_index']}:{hit['_id']}"
                    alert = hit["_source"]
                except (KeyError, TypeError):
                    # One malformed hit must not wedge the cursor forever; skip it loudly.
                    log.warning("skipped a Wazuh hit with no _index/_id/_source")
                    continue
                if external_id in self._seen:
                    continue
                self._seen[external_id] = end
                # ``alert`` is passed through untouched; alerts.normalise reads the Windows fields
                # and the pipeline fills counts from the lesson's count_defaults (decision 18).
                batch.append({"source": "wazuh", "external_id": external_id,
                              "alert": alert, "shieldmate": None})

            self._last_success = end
            # Anything older than the look-back can no longer be returned by Wazuh again.
            cutoff = end - LOOKBACK
            self._seen = {k: seen_at for k, seen_at in self._seen.items() if seen_at >= cutoff}
            return batch


# --- Legacy adapter, kept for compatibility ------------------------------------------------
# These two used to live in actions/wazuh_client.py (which re-exports them lazily). The app
# does not use them: WazuhSource above plus alerts/normalise.py replace them. Safe to delete
# once nothing outside this repo imports them.

def normalise(hit: dict) -> dict:
    """Adapter shape; map this to your existing NormalisedAlert model in the repo."""
    raw = hit['_source']
    win = raw.get('data', {}).get('win', {}).get('eventdata', {})
    rule = raw.get('rule', {})
    return {
        'source': 'wazuh',  # Server assigned; never accept source from the browser.
        # Include index because _id is only unique within an index.
        'external_id': f"{hit['_index']}:{hit['_id']}",
        'rule_id': str(rule['id']), 'level': int(rule['level']),
        'agent_name': raw['agent']['name'], 'agent_id': raw['agent']['id'],
        'timestamp': raw['timestamp'],
        'source_ip': win.get('ipAddress'),
        'log_fields': {'username_tried': win.get('targetUserName')},
        # Fill failures/window from Ishaan's installed 60204 definition in your
        # lesson engine. Do not invent counts or infer them from description text.
        'raw': raw,
    }


class WazuhPoller:
    def __init__(self, client: WazuhClient, ingest: Callable[[dict], None], *,
                 clock: Callable[[], datetime] = utc_now, lookback_seconds: int = 120):
        self.client, self.ingest, self.clock = client, ingest, clock
        self.started_at = clock()  # Old demo alerts are excluded at startup.
        self.last_success = self.started_at
        self.lookback = timedelta(seconds=lookback_seconds)
        self.last_error: str | None = None
        self._poll_lock = threading.Lock()

    def poll_once(self) -> None:
        # Run every 5 s in your existing background task. In an async FastAPI app
        # use asyncio.to_thread(self.poll_once), not blocking I/O on the event loop.
        # Single worker; reset must stop/recreate this poller and reset the DB.
        with self._poll_lock:
            end = self.clock()
            start = max(self.started_at, self.last_success - self.lookback)
            try:
                for hit in self.client.alert_hits(start, end):
                    # ingest MUST atomically dedupe external_id and perform the
                    # shared filter/group/store/proposal transaction. A duplicate
                    # must do nothing; no in-memory _seen and no block call here.
                    self.ingest(normalise(hit))
            except Exception:
                self.last_error = 'Live ingestion failed; use Backstage replay'
                raise  # Supervisor logs sanitized failure and retries next tick.
            else:
                self.last_success = end  # Never advance after partial failure.
                self.last_error = None
