"""Real backup/restore verification (restore/verify.py): the recovery/patch drill.

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
    # build() also drops the verify trees next to backup: compromised/, patched/, vuln_markers.json.
    make.build(tmp_path / "orig", tmp_path / "backup", good=good, now_text="2026-11-01T04:00:00Z")
    config = Config(
        db_path=tmp_path / "unused.db",
        restore_backup_dir=tmp_path / "backup",
        restore_manifest=tmp_path / "orig" / "manifest.json",
        restore_sandbox_dir=tmp_path / "sandbox")
    return db, FakeClock(), config


def _marker_list(config: Config) -> list[str]:
    markers = config.restore_backup_dir.parent / "vuln_markers.json"
    return __import__("json").loads(markers.read_text(encoding="utf-8"))["markers"]


def _tree(base: Path) -> dict[str, bytes]:
    return {str(p.relative_to(base)): p.read_bytes() for p in Path(base).rglob("*") if p.is_file()}


def test_verify_passes_on_a_clean_backup(tmp_path):
    db, clock, config = _setup(tmp_path, good=True)
    out = verify.run_verify(db, clock, config)
    assert out["result"] == "PASS" and all(c["passed"] for c in out["checks"])
    # The drill: 3 planted vulnerabilities, all closed by the patch, backup clean.
    assert out["vulns_found"] == 3 and out["vulns_fixed"] == 3 and out["vulns_remaining"] == 0
    assert out["backup_vuln_files"] == 0
    assert out["recovery"]["files_total"] == out["recovery"]["files_ok"] == 50
    assert out["recovery"]["markers_in_recovered"] == 0
    assert [c["check"] for c in out["checks"]] == ["update", "vulnerabilities", "recovery"]


def test_verify_fails_when_the_demo_backup_is_corrupt(tmp_path):
    db, clock, config = _setup(tmp_path, good=False)
    out = verify.run_verify(db, clock, config)
    assert out["result"] == "FAIL"
    by = {c["check"]: c for c in out["checks"]}
    # The patch still closes the live vulnerabilities; the recovery is what breaks
    # (the two altered files hash wrong against the manifest).
    assert by["update"]["passed"] and by["vulnerabilities"]["passed"]
    assert not by["recovery"]["passed"] and out["recovery"]["files_ok"] == 48


def test_verify_fails_when_the_patch_leaves_a_hole(tmp_path):
    db, clock, config = _setup(tmp_path, good=True)
    # Drop the patch for one vulnerable file: that marker survives the "update".
    (config.restore_backup_dir.parent / "patched" / "invoices" / "invoice_005.txt").unlink()
    out = verify.run_verify(db, clock, config)
    assert out["result"] == "FAIL"
    by = {c["check"]: c for c in out["checks"]}
    assert not by["update"]["passed"]
    assert out["vulns_found"] == 3 and out["vulns_remaining"] == 1


def test_verify_flags_a_backup_that_carries_vulnerabilities(tmp_path):
    db, clock, config = _setup(tmp_path, good=True)
    # A backup that still contains a marker restores the holes - both the compare
    # and the recovery scan must catch it.
    marker = _marker_list(config)[0]
    f = config.restore_backup_dir / "invoices" / "invoice_003.txt"
    f.write_bytes(f.read_bytes() + f"# VULNERABLE: {marker}\n".encode("utf-8"))
    out = verify.run_verify(db, clock, config)
    assert out["result"] == "FAIL"
    by = {c["check"]: c for c in out["checks"]}
    assert out["backup_vuln_files"] == 1
    assert not by["vulnerabilities"]["passed"]
    assert out["recovery"]["markers_in_recovered"] == 1
    # The hash of that file no longer matches the manifest either.
    assert "invoices/invoice_003.txt" in by["recovery"]["failed_files"]


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
