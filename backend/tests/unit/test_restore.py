"""Restore checker: T1.12 (demo backup FAILs all three checks), T1.13 (a good backup
PASSes), T1.14 (the checker writes only to the sandbox)."""
from __future__ import annotations

from pathlib import Path

from clock import FakeClock
from config import Config
from db import connect
from demo_backup import make
from restore import checker


def _setup(tmp_path: Path, good: bool):
    """A seeded DB plus a generated backup/manifest pointed at by a throwaway config."""
    db = connect(Config(db_path=tmp_path / "db.sqlite"))
    make.build(tmp_path / "orig", tmp_path / "backup", good=good, now_text="2026-11-01T04:00:00Z")
    config = Config(
        db_path=tmp_path / "unused.db",
        restore_backup_dir=tmp_path / "backup",
        restore_manifest=tmp_path / "orig" / "manifest.json",
        restore_sandbox_dir=tmp_path / "sandbox")
    return db, FakeClock(), config


def test_demo_backup_fails_all_three_checks(tmp_path):
    db, clock, config = _setup(tmp_path, good=False)
    out = checker.run(db, clock, config)
    # 9 days old > the 24h limit, 48/50 hash, always connected -> FAIL (T1.12).
    assert out["result"] == "FAIL"
    assert out["exposed"] is True
    assert out["files_total"] == 50 and out["files_ok"] == 48
    by = {c["check"]: c for c in out["checks"]}
    assert not (by["freshness"]["passed"] or by["integrity"]["passed"] or by["exposure"]["passed"])
    assert by["integrity"]["failed_files"] == ["invoices/invoice_017.txt", "letters/letter_032.txt"]
    assert out["simulated_backup"] is False        # custom dir -> not the demo's simulated backup
    assert db.one("SELECT result FROM restore_runs")["result"] == "FAIL"


def test_good_backup_passes(tmp_path):
    db, clock, config = _setup(tmp_path, good=True)
    out = checker.run(db, clock, config)
    assert out["result"] == "PASS"
    assert all(c["passed"] for c in out["checks"])
    assert out["files_ok"] == out["files_total"] == 50
    assert out["exposed"] is False                 # T1.13


def test_checker_writes_only_to_the_sandbox(tmp_path):
    db, clock, config = _setup(tmp_path, good=False)
    backup = config.restore_backup_dir
    before = {p.name for p in backup.iterdir()}
    sandbox = config.restore_sandbox_dir
    checker.run(db, clock, config)
    # The backup folder is untouched (T1.14); the sandbox now holds the copy.
    assert {p.name for p in backup.iterdir()} == before
    assert (sandbox / "invoices" / "invoice_017.txt").is_file()
    assert (sandbox / "backup_meta.json").is_file()


def test_latest_is_not_tested_before_any_run(tmp_path):
    db, clock, config = _setup(tmp_path, good=False)
    assert checker.latest(db, config) == {
        "id": None, "result": "NOT_TESTED", "simulated_backup": False, "started_at": None,
        "backup_age_hours": None, "files_total": None, "files_ok": None, "exposed": None,
        "checks": []}


def test_latest_returns_the_newest_run(tmp_path):
    db, clock, config = _setup(tmp_path, good=False)
    checker.run(db, clock, config)
    first_id = db.one("SELECT id FROM restore_runs ORDER BY id DESC")["id"]
    clock.advance(60)
    checker.run(db, clock, config)
    latest = checker.latest(db, config)
    assert latest["id"] > first_id and latest["result"] == "FAIL"
