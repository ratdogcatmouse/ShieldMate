"""Impact priority: how much is actually at risk, so the team knows what to rush (T7).

The "boss vs receptionist" rule, made numeric (roadmap 2.2):

    score = services_at_risk_weight x damage_state_weight + account_weight

- services: the seed's service weights for the device (keys normalised to lowercase).
- damage:   how bad things are on that device right now - a table in the seed's
  ``impact`` block, read the way ``lessons.json`` is read (no schema change).
- account:  which account the threat reaches, so a phished owner PC outranks a
  reception PC even though it "only" runs consultations.

Worked examples with the shipped seed weights (the T7.02 fixtures):

    60204 on RECEPTION-PC  = 2 x 1 + 2  =  4   low
    60204 on FILE-SERVER   = 13 x 1 + 3 = 16   high
    100201 on FILE-SERVER  = 13 x 3 + 0 = 39   critical
    61320 on DOCTOR-PC     = 3 x 2 + 5  = 11   high

Note the roadmap's prose maps "new 60204 -> compromised"; the normative worked
examples score it at x1, which is what "threat at the door, no confirmed break-in
yet" means - 60204 is "isolated" (1). 60106 (a login that succeeded) is "infected" (2).

Pure lookups - "it's a lookup, which is honest and enough" (design doc).
"""
from __future__ import annotations

import json
from pathlib import Path

from contract import ImpactOut

# Damage state when a rule has no entry of its own: a threat at the door, no damage yet.
_DEFAULT_RULE = {"damage": "isolated", "account": "device"}
# The device strip has no rule context: an under_attack device is a threat at the door.
_STRIP_STATE = "isolated"


class ImpactError(ValueError):
    """The seed's impact block breaks the T7.01 rules."""


class ImpactBook:
    """The seed's impact block, loaded and validated once per seed path.

    Shaped like this (backend/seed/clinic.json, top-level "impact" key):

        "impact": {
            "services": {"patient records": 5, ...},
            "accounts": {"owner": 5, "billing": 3, "front_desk": 2},
            "damage":   {"encrypted": 3, "infected": 2, "compromised": 2,
                         "isolated": 1, "ok": 0},
            "bands": [4, 8, 16],
            "device_accounts": {"RECEPTION-PC": "front_desk", ...},
            "rules": {"60204": {"damage": "isolated", "account": "device"}, ...}
        }
    """

    def __init__(self, data: dict, damage: dict):
        self.data = data
        # Scenario device states (the design's enum: infected / isolated /
        # encrypting / encrypted / ok) map onto the same damage weights.
        self._damage = {**damage, "encrypting": 3}

    @classmethod
    def load(cls, seed_path: Path) -> "ImpactBook":
        clinic = json.loads(Path(seed_path).read_text(encoding="utf-8"))
        block = clinic.get("impact")
        if not block:
            # No impact block (an older seed): the feature degrades to "no impact"
            # instead of the server refusing to start - same rule as every flag.
            return cls({}, {})
        return cls.validate(block)

    @classmethod
    def validate(cls, block: dict) -> "ImpactBook":
        """All the T7.01 rules; raises ``ImpactError`` naming the first break."""
        for name, table in (("services", block.get("services") or {}),
                            ("accounts", block.get("accounts") or {}),
                            ("damage", block.get("damage") or {})):
            for key, value in table.items():
                if not isinstance(value, (int, float)) or value < 0:
                    raise ImpactError(f"impact.{name}[{key!r}] must be a non-negative number")
        damage = block.get("damage") or {}
        for state in ("encrypted", "infected", "compromised", "isolated", "ok"):
            if state not in damage:
                raise ImpactError(f"impact.damage is missing {state!r}")
        bands = block.get("bands")
        if not (isinstance(bands, list) and len(bands) == 3
                and all(isinstance(b, (int, float)) for b in bands)
                and bands[0] < bands[1] < bands[2]):
            raise ImpactError("impact.bands must be three ascending thresholds [low, medium, high]")
        return cls(block, damage)

    # --- lookups -------------------------------------------------------------

    def services_weight(self, device: dict) -> int:
        """The seed weights for a device's services (keys normalised to lowercase)."""
        return sum(int(self.data.get("services", {}).get(s.lower(), 0))
                   for s in (device.get("services") or []))

    def account_weight(self, agent_name: str, account_mode: str) -> int:
        """Which account the threat reaches: the device's account, or none (file events)."""
        if account_mode == "device":
            key = (self.data.get("device_accounts") or {}).get(agent_name)
            return int((self.data.get("accounts") or {}).get(key, 0))
        return 0

    def damage_weight(self, state: str) -> int:
        return int(self._damage.get(state, 0))

    def band(self, score: int) -> str:
        """low / medium / high / critical for a score, against the seed's thresholds."""
        bands = self.data.get("bands", [4, 8, 16])
        if score <= bands[0]:
            return "low"
        if score <= bands[1]:
            return "medium"
        if score <= bands[2]:
            return "high"
        return "critical"

    def rule_map(self, rule_id: str) -> dict:
        return (self.data.get("rules") or {}).get(str(rule_id), _DEFAULT_RULE)


_BOOKS: dict[Path, ImpactBook] = {}


def book_for(seed_path: Path) -> ImpactBook:
    """The seed's impact block, loaded and validated once per seed path."""
    key = Path(seed_path).resolve()
    if key not in _BOOKS:
        _BOOKS[key] = ImpactBook.load(key)
    return _BOOKS[key]


# --- the two surfaces ----------------------------------------------------------

def alert_out(book: ImpactBook | None, device: dict | None, rule_id: str,
              status: str) -> dict | None:
    """The ``ImpactOut`` object for an alert (T7.03), or None when the alert is
    filtered noise, the device is unknown, or nothing is at risk.

    The reason string is generated, never free text (roadmap 2.3): one place to
    read it, so it can't drift between the card, the strip and the log.
    """
    if book is None or book.data is None or device is None or status == "filtered":
        return None
    rule = book.rule_map(rule_id)
    score = book.services_weight(device) * book.damage_weight(rule["damage"]) \
        + book.account_weight(device["agent_name"], rule.get("account", "none"))
    if score == 0:
        return None
    level = book.band(score)
    services = ", ".join(s.lower() for s in device.get("services") or []) or "its services"
    account = (book.data.get("device_accounts") or {}).get(device["agent_name"])
    why = f"{services} on {device['agent_name']}" + (f" ({account} account)" if account else "")
    return {"level": level, "score": score, "reason": f"{level.capitalize()} - {score}: {why}"}


def device_strip(book: ImpactBook | None, device: dict) -> dict | None:
    """The ``ImpactOut`` object for the owner strip (T7.04): the exposure at a glance.

    Only an ``under_attack`` device has open exposure (a threat at the door);
    ok and protected mean nothing is at risk right now, so they get None.
    """
    if book is None or book.data is None or device["status"] != "under_attack":
        return None
    score = book.services_weight(device) * book.damage_weight(_STRIP_STATE) \
        + book.account_weight(device["agent_name"], "device")
    if score == 0:
        return None
    level = book.band(score)
    services = ", ".join(s.lower() for s in device.get("services") or []) or "its services"
    account = (book.data.get("device_accounts") or {}).get(device["agent_name"])
    why = f"{services} on {device['agent_name']} under attack" + (f" ({account} account)" if account else "")
    return {"level": level, "score": score, "reason": f"{level.capitalize()} - {score}: {why}"}


def step_exposure(book: ImpactBook | None, devices: list[dict], step: dict) -> int:
    """What a scenario step put at risk (T7.06): every device the step declared,
    scored against the step's own state, summed. Feeds ``top_missed_impact``."""
    if book is None or book.data is None:
        return 0
    by_agent = {d["agent_name"]: d for d in devices}
    total = 0
    for agent, state in (step.get("devices") or {}).items():
        d = by_agent.get(agent)
        if d is None:
            continue
        total += book.services_weight(d) * book.damage_weight(state)
    return total


def notification_prefix(impact_obj: dict | None) -> str:
    """High/critical alerts get a prefix in the owner's notification (roadmap 2.3);
    low and medium stay as they always were (the T1.02 test relies on that)."""
    if impact_obj and impact_obj["level"] in ("high", "critical"):
        return f"[{impact_obj['level'].upper()}] "
    return ""


# Re-export for type checkers importing the model alongside the engine.
__all__ = ["ImpactOut", "ImpactBook", "ImpactError", "book_for",
           "alert_out", "device_strip", "step_exposure", "notification_prefix"]
