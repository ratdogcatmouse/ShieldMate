"""Backup / restore verification: does a backup of a compromised directory carry the same
vulnerabilities as the live system?

The demo directories stay synthetic, but the feature does the real work it claims. Three
steps, exactly the story:

1. **backup** - the compromised live directory (``compromised/``) is copied into the
   sandbox as the backup of the compromised state, and scanned for vulnerability markers.
2. **update** - the IT patch (``patched/``) is applied to a *sandbox copy* of the live
   directory - the live trees are never modified (T1.14: the sandbox is the only folder
   this module writes to) - and re-scanned.
3. **compare** - the updated directory and the backup are scanned for the same markers:
   does the backup still carry the vulnerabilities? If it does, restoring that backup
   would bring the holes straight back.

Fast and deterministic: tens of small files, fixed markers, no execution.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from clock import Clock, iso
from config import Config
from db import Database
from errors import ApiError


def _dirs(config: Config):
    """The verify story lives next to the backup folder (demo_backup/ by default)."""
    base = config.restore_backup_dir.parent
    return base / "compromised", base / "patched", base / "vuln_markers.json"


def _ensure_trees(config: Config) -> tuple[Path, Path, Path]:
    from demo_backup import make
    compromised, patched, markers = _dirs(config)
    if not markers.is_file():
        if config.restore_backup_dir == make.BACKUP_DIR:
            make.ensure()                                  # the demo layout can always regenerate
        else:
            raise ApiError("invalid_request",
                           "Backup verify needs the demo backup layout (compromised/patched trees).", 400)
    if not markers.is_file():
        raise ApiError("not_found", "Verify demo trees are missing; press Reset.", 404)
    return compromised, patched, markers


def _markers(markers_path: Path) -> list[str]:
    return json.loads(markers_path.read_text(encoding="utf-8"))["markers"]


def _walk_files(base: Path) -> list[Path]:
    return sorted(p for p in Path(base).rglob("*") if p.is_file())


def _scan(base: Path, markers: list[str]) -> dict[str, list[str]]:
    """rel path (POSIX form) -> markers found, only for files that carry at least one marker."""
    out: dict[str, list[str]] = {}
    for f in _walk_files(base):
        text = f.read_bytes().decode("utf-8", errors="replace")
        hit = [m for m in markers if m in text]
        if hit:
            out[f.relative_to(base).as_posix()] = hit
    return out


def _apply_patch(source: Path, patched: Path, target: Path) -> None:
    """Copy the IT patch onto ``target``, keeping the patch's relative layout."""
    for rel in _walk_files(patched):
        dest = target / Path(rel).relative_to(patched)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(rel, dest)


def snapshot_only(db: Database, clock: Clock, config: Config) -> dict:
    """Back up the compromised directory now, without running the full verify.

    No alert/DB writes - the snapshot is pure filesystem, in the sandbox (T1.14).
    Raises ApiError on a missing/unsupported layout - fine for a route call, wrong
    for an automatic hook; use ``auto_snapshot`` for that.
    """
    compromised, _, markers_path = _ensure_trees(config)
    markers = _markers(markers_path)
    snap = config.restore_sandbox_dir / "snapshot"
    shutil.rmtree(snap, ignore_errors=True)
    shutil.copytree(compromised, snap)
    vuln = _scan(snap, markers)
    report = {"files": len(_walk_files(snap)), "vuln_files": len(vuln)}
    db.emit("restore.snapshot", subject=("restore_run", None), files=report["files"],
            vuln_files=report["vuln_files"])
    return report


def auto_snapshot(db: Database, clock: Clock, config: Config) -> dict | None:
    """The pipeline-safe variant of ``snapshot_only`` (the 100201 created-card hook).

    Ishaan's lane calls this when an encryption card is created, so the compromised
    state is backed up automatically. It must never crash the pipeline: the demo
    layout snapshots (regenerating missing trees), any other layout (a real backup
    drive) is a quiet no-op, and a broken demo layout just logs nothing.
    """
    if not _is_demo_layout(config):
        return None
    try:
        return snapshot_only(db, clock, config)
    except Exception:
        # An automatic hook must never take the alert pipeline down (T5.09 rule);
        # a broken layout just means no snapshot this time.
        return None


def run_verify(db: Database, clock: Clock, config: Config) -> dict:
    """Back up the compromised directory, update the live directory, then compare the two.

    1. **backup** the compromised state - copy ``compromised/`` into the sandbox and
       scan it for vulnerability markers: this is what the backup now carries.
    2. **update** the live directory - apply the IT patch to a sandbox copy and re-scan.
    3. **compare** - does the backup still hold a marker the updated directory no longer
       has? If yes, restoring that backup would reintroduce the compromise.

    ``result`` is PASS only when the update closed every vulnerability the live directory
    carried AND the backup carries none of them.
    """
    compromised, patched, markers_path = _ensure_trees(config)
    markers = _markers(markers_path)
    sandbox = config.restore_sandbox_dir
    shutil.rmtree(sandbox, ignore_errors=True)
    sandbox.mkdir(parents=True)
    checks: list[dict] = []

    # 1. BACKUP the compromised directory - the backup of the compromised state now
    #    captures whatever vulnerabilities the live directory had at that moment.
    backup = sandbox / "backup"
    shutil.copytree(compromised, backup)
    backup_vuln = _scan(backup, markers)
    backup_vuln_files = len(backup_vuln)

    # 2. UPDATE the live directory - on a sandbox copy, never the real trees - and re-scan.
    updated = sandbox / "updated"
    shutil.copytree(compromised, updated)
    _apply_patch(updated, patched, updated)
    updated_vuln = _scan(updated, markers)
    updated_vuln_files = len(updated_vuln)
    checks.append({
        "check": "update",
        "passed": updated_vuln_files == 0,
        "detail": (f"{sum(len(v) for v in backup_vuln.values())} vulnerability marker(s) in the live "
                   f"directory, {updated_vuln_files} after the update."
                   + (" All closed." if updated_vuln_files == 0 else " Still open after the update.")),
        "fix": "Apply the vendor patch and re-verify before trusting the update.",
    })

    # 3. COMPARE the updated directory with the backup - does the backup have the same
    #    vulnerabilities? The backup is a snapshot of the compromised state; a marker it
    #    carries that the updated directory no longer has is one a restore would bring
    #    straight back. (Markers still present after the update are caught by the "update"
    #    check above; this one is about the backup specifically.)
    backup_markers = {m for marks in backup_vuln.values() for m in marks}
    updated_markers = {m for marks in updated_vuln.values() for m in marks}
    stale = backup_markers - updated_markers          # in the backup, gone from the live dir
    checks.append({
        "check": "compare",
        "passed": not stale,
        "detail": ("The backup carries no vulnerability the updated directory lacks; "
                   "restoring it is safe."
                   if not stale else
                   f"The backup still carries {len(stale)} vulnerability marker(s) the update removed "
                   f"from the live directory (e.g. {sorted(stale)[0]}). Restoring it would bring the "
                   "vulnerabilities back."),
        "fix": "Take a new backup after the update and verify again.",
    })

    result = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    now_text = iso(clock.now())
    # The shared restore_runs table stores files_total/files_ok: total = the backup's
    # file count, ok = the files that carry no marker after the update.
    files_total = len(_walk_files(backup))
    files_ok = files_total - updated_vuln_files
    run_id = db.execute(
        "INSERT INTO restore_runs (kind, started_at, result, backup_age_hours, files_total,"
        " files_ok, exposed, details) VALUES ('verify', ?, ?, 0, ?, ?, 0, ?)",
        (now_text, result, files_total, files_ok, json.dumps(checks)))
    db.emit("restore.verify", subject=("restore_run", run_id), result=result,
            backup_vuln_files=backup_vuln_files, updated_vuln_files=updated_vuln_files,
            same_vulnerabilities=bool(stale))
    return {
        "id": run_id,
        "kind": "verify",
        "started_at": now_text,
        "result": result,
        "simulated_backup": _is_demo_layout(config),
        "backup_vuln_files": backup_vuln_files,
        "updated_vuln_files": updated_vuln_files,
        "same_vulnerabilities": bool(stale),
        "checks": checks,
    }


def _is_demo_layout(config: Config) -> bool:
    from demo_backup import make
    return config.restore_backup_dir == make.BACKUP_DIR
