"""Scenario files: load and validate the drill JSON (T0.04).

A scenario is the "script" a drill runs: four phases (detect, contain, recover,
report) with role-split options. The engine only ever sees validated dicts from
here, so a broken scenario fails fast at load, never mid-drill on a phone.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from contract import ActionId, Phase, ScenarioDeviceState

_PHASES = set(get_args(Phase))
_DEVICE_STATES = set(get_args(ScenarioDeviceState))
_ACTION_IDS = set(get_args(ActionId))
# Spec: the only trigger a scenario option may carry.
_ALLOWED_TRIGGERS = {"restore_check"}
# "staff" in the file covers the two non-owner roles; the owner gets their own list.
# A step may also give one non-owner role its own list ("front_desk" or "billing"), which
# then replaces "staff" for that role only (e.g. Ravi's payment choices in supplier_bank_fraud).
_STAFF_ROLES = ("front_desk", "billing")
_ROLE_KEYS = ("staff", "owner") + _STAFF_ROLES


class ScenarioError(ValueError):
    """The scenario file breaks the T0.04 validation rules."""


def load_scenario(path: Path) -> dict:
    """Load one scenario file and return it, raising ``ScenarioError`` if it is broken."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_scenario(data)
    return data


def load_scenarios(dir_path: Path) -> dict[str, dict]:
    """Every ``*.json`` in the folder, keyed by ``scenario_id``."""
    out: dict[str, dict] = {}
    for f in sorted(Path(dir_path).glob("*.json")):
        data = load_scenario(f)
        out[data["scenario_id"]] = data
    return out


def validate_scenario(data: dict, device_names: set[str] | None = None) -> None:
    """All the spec's T0.04 rules; raises ``ScenarioError`` naming the first break.

    ``device_names`` (the seed's agent names, if passed) also has to cover every device
    a step declares.
    """
    sid = data.get("scenario_id", "?")
    if "title" not in data or not isinstance(data.get("steps"), list) or not data["steps"]:
        raise ScenarioError(f"{sid}: needs a title and a non-empty steps list")

    seen_ids: set[str] = set()
    for step in data["steps"]:
        label = f"{sid}/{step.get('step_id', '?')}"
        if step.get("step_id") in seen_ids:
            raise ScenarioError(f"{label}: duplicate step_id")
        seen_ids.add(step["step_id"])
        if step.get("phase") not in _PHASES:
            raise ScenarioError(f"{label}: phase {step.get('phase')!r} is not in the enum")

        # Device states must be from the scenario enum; names against the seed if given.
        for device, state in (step.get("devices") or {}).items():
            if state not in _DEVICE_STATES:
                raise ScenarioError(f"{label}: {device} has unknown state {state!r}")
            if device_names is not None and device not in device_names:
                raise ScenarioError(f"{label}: unknown device {device!r}")

        # Each role's options: IDs unique in the step, action IDs from the fixed
        # vocabulary, triggers from the allowed set, exactly one correct.
        for role_key, options in (step.get("options") or {}).items():
            where = f"{label}/{role_key}"
            if role_key not in _ROLE_KEYS:
                raise ScenarioError(f"{where}: unknown role key")
            n_correct = 0
            seen_opts: set[str] = set()
            for opt in options:
                if opt.get("option_id") in seen_opts:
                    raise ScenarioError(f"{where}: duplicate option {opt.get('option_id')!r}")
                seen_opts.add(opt["option_id"])
                for act in opt.get("actions", []):
                    if act not in _ACTION_IDS:
                        raise ScenarioError(f"{where}: unknown action {act!r}")
                if not option_triggers(opt) <= _ALLOWED_TRIGGERS:
                    raise ScenarioError(f"{where}: unknown trigger in {opt.get('triggers')!r}")
                if opt.get("correct") is True:
                    n_correct += 1
            # A role that has options must have exactly one correct one (T0.04).
            if options and n_correct != 1:
                raise ScenarioError(f"{where}: a role with options needs exactly one correct option, got {n_correct}")


def options_for(step: dict, role: str) -> list[dict]:
    """The options a player of ``role`` sees at ``step`` (empty when the role has none).

    The owner reads "owner"; front_desk/billing read their own key when the step has one,
    else the shared "staff" list. The engine and scoring both call this, so who-sees-what
    can never differ between the phone and the results screen.
    """
    options = step.get("options") or {}
    if role == "owner":
        return options.get("owner", [])
    if role in options:
        return options[role]
    return options.get("staff", [])


def option_triggers(option: dict) -> set[str]:
    """The ``triggers`` of one option as a set (the file stores it as a bare string
    or a list; missing means none)."""
    t = option.get("triggers")
    return {t} if isinstance(t, str) else set(t or [])


def devices_of(step: dict) -> dict[str, str]:
    """The step's device states; a step may declare none (all devices stay OK)."""
    return step.get("devices") or {}
