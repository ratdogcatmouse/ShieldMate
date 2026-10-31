"""Scenario and demo-backup data rules: T0.04 (scenarios load and validate) and
T0.06 (the backup generator's faults)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from demo_backup import make
from drills import models

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"


def test_shipped_scenarios_validate():
    scenarios = models.load_scenarios(SCENARIOS_DIR)
    assert set(scenarios) == {"ransomware_clinic", "password_guessing",
                              "phish_doctor_email", "tech_support_call", "supplier_bank_fraud"}
    assert len(scenarios["ransomware_clinic"]["steps"]) == 4
    assert len(scenarios["password_guessing"]["steps"]) == 2
    # Both load, so the files pass their own T0.04 rules (unique step ids, one correct per role).


def test_unique_step_ids_and_roles():
    data = models.load_scenario(SCENARIOS_DIR / "ransomware_clinic.json")
    ids = [s["step_id"] for s in data["steps"]]
    assert len(ids) == len(set(ids))
    for step in data["steps"]:
        assert set(step["options"]) <= {"staff", "owner"}


def test_bad_triggers_rejected():
    data = models.load_scenario(SCENARIOS_DIR / "password_guessing.json")
    data["steps"][0]["options"]["staff"][0]["triggers"] = "something_else"
    with pytest.raises(models.ScenarioError):
        models.validate_scenario(data)


def test_duplicate_step_id_rejected():
    data = models.load_scenario(SCENARIOS_DIR / "password_guessing.json")
    data["steps"][1]["step_id"] = data["steps"][0]["step_id"]
    with pytest.raises(models.ScenarioError):
        models.validate_scenario(data)


def test_two_correct_options_rejected():
    data = models.load_scenario(SCENARIOS_DIR / "password_guessing.json")
    data["steps"][0]["options"]["staff"][0]["correct"] = True
    with pytest.raises(models.ScenarioError):
        models.validate_scenario(data)


def test_unknown_device_state_rejected():
    data = models.load_scenario(SCENARIOS_DIR / "password_guessing.json")
    data["steps"][0]["devices"]["RECEPTION-PC"] = "exploded"
    with pytest.raises(models.ScenarioError):
        models.validate_scenario(data)


# --- T0.06: the demo backup generator -----------------------------------------

def test_backup_has_50_originals_with_matching_manifest(tmp_path):
    manifest = make.build(tmp_path / "o", tmp_path / "b", good=False, now_text="2026-11-01T04:00:00Z")
    originals = tmp_path / "o"
    assert len(manifest) == 50
    assert set(manifest) == {p.relative_to(originals).as_posix() for p in originals.rglob("*.txt")}
    # Every listed file hashes to the manifest's original value.
    import hashlib
    for rel, hexdigest in manifest.items():
        assert hashlib.sha256((originals / rel).read_text().encode("utf-8")).hexdigest() == hexdigest


def test_backup_differs_in_exactly_two_files_and_is_nine_days_old(tmp_path):
    now_text = "2026-11-01T04:00:00Z"
    manifest = make.build(tmp_path / "o", tmp_path / "b", good=False, now_text=now_text)
    originals, backup = tmp_path / "o", tmp_path / "b"
    bad = [rel for rel in manifest
           if (backup / rel).read_text() != (originals / rel).read_text()]
    assert sorted(bad) == sorted(make.ALTERED_FILES) == ["invoices/invoice_017.txt", "letters/letter_032.txt"]
    meta = json.loads((backup / "backup_meta.json").read_text())
    assert meta["always_connected"] is True
    assert meta["last_backup_at"] == "2026-10-23T04:00:00Z"          # exactly 9 days old


def test_good_backup_is_clean_and_fresh(tmp_path):
    now_text = "2026-11-01T04:00:00Z"
    manifest = make.build(tmp_path / "o", tmp_path / "b", good=True, now_text=now_text)
    originals, backup = tmp_path / "o", tmp_path / "b"
    assert all((backup / rel).read_text() == (originals / rel).read_text() for rel in manifest)
    meta = json.loads((backup / "backup_meta.json").read_text())
    assert meta == {"last_backup_at": now_text, "always_connected": False}


def test_content_is_deterministic(tmp_path):
    m1 = make.build(tmp_path / "o1", tmp_path / "b1", good=False, now_text="2026-11-01T04:00:00Z")
    m2 = make.build(tmp_path / "o2", tmp_path / "b2", good=False, now_text="2026-11-01T04:00:00Z")
    assert m1 == m2                       # same hashes on every machine/run
