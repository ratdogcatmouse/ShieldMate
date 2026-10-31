"""Impact meter: what a step's device states mean for the clinic's services (T2.06).

A step declares device states (``{"FILE-SERVER": "encrypting"}``). This module joins
them with the seed's ``devices.services`` and ``when_down`` notes - a pure lookup, no
simulation (design doc: "it's a lookup, which is honest and enough").

The rule follows the design's Appendix A table: a healthy device shows its services
"ok"; a compromised one (infected / isolated / encrypting / encrypted) shows each
service as "moved" with the device's when_down note ("Check-in moves to the billing PC")
where such a note exists, and "down" otherwise.
"""
from __future__ import annotations

# Scenario states that mean "something is wrong with this device".
COMPROMISED = {"infected", "isolated", "encrypting", "encrypted"}


def step_impact(step: dict, devices: list[dict]) -> list[dict]:
    """The drill view's ``impact`` list for one step, in seed device order.

    ``devices`` is ``db.devices()`` (services and when_down already decoded).
    A device not named in the step's ``devices`` map stays "ok".
    """
    states = step.get("devices") or {}
    out: list[dict] = []
    for d in devices:
        state = states.get(d["agent_name"], "ok")
        if state not in COMPROMISED:
            # Healthy: every service runs as normal.
            out.append({"device": d["agent_name"], "state": state,
                        "services": [{"name": s, "status": "ok"} for s in d["services"]]})
            continue
        # Compromised: each service moves (the when_down note) or goes down.
        services: list[dict] = []
        for s in d["services"]:
            note = d["when_down"].get(s)
            if note:
                services.append({"name": s, "status": "moved", "note": note})
            else:
                services.append({"name": s, "status": "down"})
        out.append({"device": d["agent_name"], "state": state, "services": services})
    return out
