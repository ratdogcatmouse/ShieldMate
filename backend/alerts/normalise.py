"""Raw Wazuh alert JSON -> ``NormalisedAlert``."""
from __future__ import annotations

from dataclasses import dataclass, field

from ingest.source import RawAlert


@dataclass
class NormalisedAlert:
    source: str
    external_id: str | None
    rule_id: str
    level: int
    agent_name: str
    timestamp: str                                           # ISO UTC
    log_fields: dict[str, str] = field(default_factory=dict)  # verbatim: username_tried, source_ip, sender
    counts: dict[str, int] = field(default_factory=dict)      # count, window_minutes, files_renamed
    raw: dict = field(default_factory=dict)

    @property
    def group_key(self) -> str:
        return f"{self.rule_id}:{self.agent_name}"


def normalise(raw: RawAlert, now: str) -> NormalisedAlert:
    alert = raw["alert"]
    eventdata = alert.get("data", {}).get("win", {}).get("eventdata", {})

    # Untrusted text: copied exactly as received, never trimmed or cleaned (T2.03).
    log_fields: dict[str, str] = {}
    if "targetUserName" in eventdata:
        log_fields["username_tried"] = str(eventdata["targetUserName"])
    if "ipAddress" in eventdata:
        log_fields["source_ip"] = str(eventdata["ipAddress"])
    # v4: an email alert's sender, so staff can see a lookalike address one letter off.
    # Attacker-controlled text like the rest: shown as plain text, never sent to the AI.
    mail = alert.get("mail") or {}
    if "from" in mail:
        log_fields["sender"] = str(mail["from"])

    # Counts for the card placeholders, taken from the optional shieldmate block.
    # DECISIONS departure #3: the replay file says "failures"; the card placeholder is {count}.
    block = raw.get("shieldmate") or {}
    counts: dict[str, int] = {}
    if "failures" in block:
        counts["count"] = int(block["failures"])
    elif "count" in block:
        counts["count"] = int(block["count"])
    for key in ("window_minutes", "files_renamed"):
        if key in block:
            counts[key] = int(block[key])

    return NormalisedAlert(
        source=raw["source"],
        external_id=raw.get("external_id"),
        rule_id=str(alert["rule"]["id"]),
        level=int(alert["rule"]["level"]),
        agent_name=alert["agent"]["name"],
        timestamp=alert.get("timestamp") or now,
        log_fields=log_fields,
        counts=counts,
        raw=alert,
    )
