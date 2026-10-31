"""The Wazuh client seam.

DECISIONS.md gives the real httpx client to Kishaann; this file ships the protocol, the
exception types and ``FakeWazuhClient`` so the approval flow never waits for the lab.
Kishaann adds ``RealWazuhClient`` here (``main.create_app`` picks it up automatically when
``ALERT_SOURCE=wazuh``).
"""
from __future__ import annotations

from typing import Protocol


class WazuhUnavailable(Exception):
    """The Wazuh API or indexer did not answer within the timeout."""


class UndoNotSupported(Exception):
    """Raised by ``unblock_ip`` when lab test T5.07 showed the unblock script doesn't work."""


class WazuhClient(Protocol):
    def block_ip(self, agent_id: str, ip: str) -> dict: ...      # raises WazuhUnavailable
    def unblock_ip(self, agent_id: str, ip: str) -> dict: ...    # raises UndoNotSupported
    def health(self) -> dict: ...                                 # {api_ok, indexer_ok, agent_active}


class FakeWazuhClient:
    """Records every call in ``.calls`` and sends nothing. Used by every test except Gate T5."""

    def __init__(self, fail_with: Exception | None = None):
        self.calls: list[tuple[str, str, str]] = []
        self.fail_with = fail_with          # tests set this to simulate a Wazuh outage

    def block_ip(self, agent_id: str, ip: str) -> dict:
        self.calls.append(("block_ip", agent_id, ip))
        if self.fail_with:
            raise self.fail_with
        return {"fake": True, "agent_id": agent_id, "ip": ip}

    def unblock_ip(self, agent_id: str, ip: str) -> dict:
        self.calls.append(("unblock_ip", agent_id, ip))
        if self.fail_with:
            raise self.fail_with
        return {"fake": True, "agent_id": agent_id, "ip": ip}

    def health(self) -> dict:
        return {"api_ok": None, "indexer_ok": None, "agent_active": None}
