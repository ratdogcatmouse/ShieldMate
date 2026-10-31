"""Backup/restore verification (restore/verify.py): back up the compromised directory, update
the live directory, then compare the two for the same vulnerabilities.

Same test pattern as test_restore.py: temp demo trees built by demo_backup.make,
a throwaway config pointing at them, and a seeded temp DB.
"""
from __future__ import annotations

from pathlib import Path

from clock import FakeClock
from config import Config
from db import connect
from demo_backup import make
from restore import verify


def _setup(tmp_path: Path, good: bool):
    db = connect(Config(db_path=tmp_path / "db.sqlite"))
    # build() drops the verify trees next to backup: compromised/, patched/, vuln_markers.json.
    make.build(tmp_path / "orig", tmp_path / "backup", good=good, now_text="2026-11-01T04:00:00Z")
    config = Config(
        db_path=tmp_path / "unused.db",
        restore_backup_dir=tmp_path / "backup",
        restore_manifest=tmp_path / "orig" / "manifest.json",
        restore_sandbox_dir=tmp_path / "sandbox")
    return db, FakeClock(), config


def _tree(base: Path) -> dict[str, bytes]:
    return {str(p.relative_to(base)): p.read_bytes() for p in Path(base).rglob("*") if p.is_file()}


def test_verify_compares_backup_against_updated_live_dir(tmp_path):
    """The demo story: the live dir carries 3 planted vulnerabilities; the patch closes all
    of them, but the backup (a snapshot of the compromised dir) still carries them - so the
    compare fails and the run is FAIL (restoring that backup would bring the holes back)."""
    db, clock, config = _setup(tmp_path, good=True)
    out = verify.run_verify(db, clock, config)
    assert out["result"] == "FAIL"
    assert [c["check"] for c in out["checks"]] == ["update", "compare"]
    # The update closed every live vulnerability...
    assert out["updated_vuln_files"] == 0
    by = {c["check"]: c for c in out["checks"]}
    assert by["update"]["passed"] is True
    # ...but the backup captured the compromised state, so it carries the same vulns.
    assert out["backup_vuln_files"] == 3
    assert out["same_vulnerabilities"] is True
    assert by["compare"]["passed"] is False


def test_verify_passes_when_the_backup_is_clean(tmp_path):
    """A live directory with no vulnerabilities produces a clean backup - PASS."""
    db, clock, config = _setup(tmp_path, good=True)
    # Point the tool at a live dir with no markers: delete the three vulnerable source files
    # so the backup (a copy of it) carries nothing and the update closes nothing to remove.
    base = config.restore_backup_dir.parent
    for rel in ("invoices/invoice_005.txt", "letters/letter_010.txt", "appointments/appt_001.txt"):
        (base / "compromised" / rel).unlink()
        (base / "patched" / rel).unlink()     # the patch no longer references these files
    out = verify.run_verify(db, clock, config)
    assert out["result"] == "PASS" and all(c["passed"] for c in out["checks"])
    assert out["backup_vuln_files"] == 0 and out["updated_vuln_files"] == 0
    assert out["same_vulnerabilities"] is False


def test_verify_fails_when_the_patch_leaves_a_hole(tmp_path):
    """An incomplete patch leaves a live vulnerability open, so the update check fails."""
    db, clock, config = _setup(tmp_path, good=True)
    base = config.restore_backup_dir.parent
    # Drop the patch for one vulnerable file: that marker survives the "update".
    (base / "patched" / "invoices" / "invoice_005.txt").unlink()
    out = verify.run_verify(db, clock, config)
    assert out["result"] == "FAIL"
    by = {c["check"]: c for c in out["checks"]}
    assert by["update"]["passed"] is False
    assert out["updated_vuln_files"] == 1


def test_snapshot_only_captures_the_compromised_state(tmp_path):
    db, clock, config = _setup(tmp_path, good=True)
    before = _tree(config.restore_backup_dir.parent / "compromised")
    report = verify.snapshot_only(db, clock, config)
    assert report == {"files": 50, "vuln_files": 3}
    assert _tree(config.restore_backup_dir.parent / "compromised") == before   # read-only
    snap = config.restore_sandbox_dir / "snapshot"
    assert len(_tree(snap)) == 50


def test_verify_writes_only_to_the_sandbox(tmp_path):
    db, clock, config = _setup(tmp_path, good=True)
    base = config.restore_backup_dir.parent
    live = {k: v for k, v in _tree(base / "compromised").items()}
    live.update(_tree(base / "patched"))
    live.update(_tree(base / "backup"))
    verify.run_verify(db, clock, config)
    # Every live tree is byte-identical afterwards; only the sandbox holds the work.
    after = {k: v for k, v in _tree(base / "compromised").items()}
    after.update(_tree(base / "patched"))
    after.update(_tree(base / "backup"))
    assert after == live


# --- auto_snapshot: the pipeline-safe hook Ishaan's lane calls on a 100201 card ---

def test_auto_snapshot_on_the_demo_layout_snapshots(tmp_path, monkeypatch):
    db, clock, config = _setup(tmp_path, good=True)
    # Pretend this temp layout IS the demo layout (and don't touch the real trees).
    monkeypatch.setattr(make, "BACKUP_DIR", config.restore_backup_dir)
    monkeypatch.setattr(make, "ensure", lambda force=False: None)
    report = verify.auto_snapshot(db, clock, config)
    assert report == {"files": 50, "vuln_files": 3}
    assert len(_tree(config.restore_sandbox_dir / "snapshot")) == 50


def test_auto_snapshot_on_a_real_layout_is_a_quiet_noop(tmp_path):
    db, clock, config = _setup(tmp_path, good=True)   # temp layout, real BACKUP_DIR
    assert verify.auto_snapshot(db, clock, config) is None
    # A real backup drive never gets a snapshot attempt.
    assert not config.restore_sandbox_dir.exists()


def test_auto_snapshot_regenerates_missing_demo_trees(tmp_path, monkeypatch):
    db, clock, config = _setup(tmp_path, good=True)
    monkeypatch.setattr(make, "BACKUP_DIR", config.restore_backup_dir)
    base = config.restore_backup_dir.parent
    for name in ("compromised", "patched"):
        import shutil
        shutil.rmtree(base / name, ignore_errors=True)
    (base / "vuln_markers.json").unlink()
    def regen():  # stand in for ensure(): rebuild the temp trees, not the real ones
        make.build(tmp_path / "orig", tmp_path / "backup",
                   now_text="2026-11-01T04:00:00Z")
    monkeypatch.setattr(make, "ensure", regen)
    assert verify.auto_snapshot(db, clock, config) == {"files": 50, "vuln_files": 3}
