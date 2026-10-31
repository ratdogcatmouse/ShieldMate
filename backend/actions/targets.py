"""Is this IP safe to block? Strict IPv4 that isn't on the explicit never-block list (T4.02)."""
from __future__ import annotations

import ipaddress


def check_target(ip: str | None, never_block: list[dict]) -> tuple[bool, str | None]:
    """Return ``(True, None)`` or ``(False, reason)``. ``never_block`` is a list of ``{ip, label}``."""
    if not ip or not isinstance(ip, str) or not ip.strip():
        return False, "There is no source address to block"
    if ip != ip.strip():
        return False, f"{ip!r} is not a valid IPv4 address"
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False, f"{ip} is not a valid IPv4 address"
    if addr.version != 4:
        return False, f"{ip} is an IPv6 address; only IPv4 can be blocked"
    for entry in never_block:
        if entry["ip"] == str(addr):
            return False, f"{ip} is {entry['label']}"
    return True, None
