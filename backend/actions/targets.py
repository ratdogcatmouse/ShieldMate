"""Is this IP safe to block? Strict IPv4 that isn't on the explicit never-block list (T4.02)."""
from __future__ import annotations

import ipaddress


def check_target(ip: str | None, never_block: list[dict]) -> tuple[bool, str | None]:
    """Return ``(True, None)`` or ``(False, reason)``. ``never_block`` is a list of ``{ip, label}``."""
    code, reason = classify(ip, never_block)
    return code is None, reason


def classify(ip: str | None, never_block: list[dict]) -> tuple[str | None, str | None]:
    """``(None, None)`` when safe, else ``(code, reason)``.

    The fixed ``code`` is what the event log stores: the reason quotes the IP, which comes
    verbatim from the alert's untrusted log fields.
    """
    if not ip or not isinstance(ip, str) or not ip.strip():
        return "no_address", "There is no source address to block"
    if ip != ip.strip():
        return "invalid_ipv4", f"{ip!r} is not a valid IPv4 address"
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "invalid_ipv4", f"{ip} is not a valid IPv4 address"
    if addr.version != 4:
        return "ipv6", f"{ip} is an IPv6 address; only IPv4 can be blocked"
    for entry in never_block:
        if entry["ip"] == str(addr):
            return "never_block", f"{ip} is {entry['label']}"
    return None, None
