"""Real backup/restore verification (the "faux" restore check made real).

The demo directories stay synthetic, but the feature does the work it claims:

1. **snapshot** - the compromised live directory (``compromised/``) is copied into
   the sandbox with a vulnerability-marker report.
2. **update**   - the IT patch (``patched/``) is applied to a *sandbox copy* of the
   live directory - the live trees are never modified (T1.14: the sandbox is the
   only folder this module writes to).
3. **vuln delta** - the snapshot and the updated copy are re-scanned for the same
   markers; the patch passes when every marker the snapshot caught is gone.
4. **recovery** - the known-good backup is restored into the sandbox and verified
   three ways: hash-integrity against the manifest, exact file-set, and a marker
   scan (a backup that restores *with* the vulnerabilities in it fails).

Fast and deterministic: tens of small files, fixed markers, no execution.
"""
from __future__ import annotations

import hashlib
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan(base: Path, markers: list[str]) -> dict[str, list[str]]:
    """rel path (POSIX form) -> markers found, only for files that carry at least one marker."""
    out: dict[str, list[str]] = {}
    for f in _walk_files(base):
        text = f.read_bytes().decode("utf-8", errors="replace")
        hit = [m for m in markers if m in text]
        if hit:
            out[f.relative_to(base).as_posix()] = hit
    return out


def snapshot_only(db: Database, clock: Clock, config: Config) -> dict:
    """Step 1 alone: back up the compromised directory now (the button/verify path).

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
    """The full story: snapshot -> update -> vuln delta -> backup comparison -> recovery test.

    1. snapshot the compromised live directory,
    2. apply the IT patch to a sandbox copy and re-scan (same markers - did the update
       close the holes the snapshot caught?),
    3. compare the *backup* against the markers (does restoring it bring the same
       vulnerabilities back?),
    4. recovery test: restore the backup into the sandbox and verify it three ways
       (hash-integrity, exact file-set, post-restore marker scan).
    """
    compromised, patched, markers_path = _ensure_trees(config)
    markers = _markers(markers_path)
    sandbox = config.restore_sandbox_dir
    shutil.rmtree(sandbox, ignore_errors=True)
    sandbox.mkdir(parents=True)
    checks: list[dict] = []

    # 1. Snapshot the compromised directory.
    snap = sandbox / "snapshot"
    shutil.copytree(compromised, snap)
    before = _scan(snap, markers)
    vulns_found = sum(len(v) for v in before.values())

    # 2. Update the live directory - on a sandbox copy, never the real trees - and re-scan.
    updated = sandbox / "updated"
    shutil.copytree(compromised, updated)
    for rel in _walk_files(patched):
        # Keep the patch's relative layout: letters/letter_010.txt lands in updated/letters/.
        target = updated / Path(rel).relative_to(patched)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(rel, target)
    after = _scan(updated, markers)
    vulns_remaining = sum(len(v) for v in after.values())
    checks.append({
        "check": "update",
        "passed": vulns_found > 0 and vulns_remaining == 0,
        "detail": (f"{vulns_found} vulnerable file(s) before the update, {vulns_remaining} after. "
                   + ("All closed." if vulns_remaining == 0 else "Still open after the update.")),
        "fix": "Apply the vendor patch and re-verify before trusting the update.",
    })

    # 3. Does the backup carry the same vulnerabilities? A read-only marker scan of the
    #    backup folder - if it does, restoring it would bring the holes back.
    backup_vuln = _scan(config.restore_backup_dir, markers)
    backup_vuln_files = len(backup_vuln)
    checks.append({
        "check": "vulnerabilities",
        "passed": backup_vuln_files == 0,
        "detail": ("The backup carries none of the known vulnerability markers."
                   if backup_vuln_files == 0 else
                   f"{backup_vuln_files} file(s) in the backup still carry a known vulnerability "
                   "marker; restoring it would bring the holes back."),
        "fix": "Rebuild the backup from the patched system.",
    })

    # 4. Recovery test: restore the known-good backup, verify it three ways.
    recovered = sandbox / "recovered"
    shutil.copytree(config.restore_backup_dir, recovered)
    manifest = json.loads(Path(config.restore_manifest).read_text(encoding="utf-8"))["files"]
    # POSIX-form keys: on Windows relative_to() gives backslashes, the manifest uses slashes.
    recovered_files = {p.relative_to(recovered).as_posix() for p in _walk_files(recovered)}
    missing = sorted(set(manifest) - recovered_files)
    bad = [rel for rel in manifest
           if (recovered / rel).is_file() and _sha256(recovered / rel) != manifest[rel]]
    # backup_meta.json is the backup's own bookkeeping, not a record file.
    extra = sorted(recovered_files - set(manifest) - {"backup_meta.json"})
    files_total = len(manifest)
    files_ok = files_total - len(missing) - len(bad)
    rec_markers = _scan(recovered, markers)
    recovery = {
        "check": "recovery",
        "passed": not missing and not bad and not extra and not rec_markers,
        "detail": (f"{files_ok} of {files_total} files restored exactly, "
                   + ("and the recovered copy is clean of every known vulnerability marker."
                      if not rec_markers else
                      f"but {len(rec_markers)} file(s) still carry a vulnerability marker.")),
        "fix": "Rebuild the backup from the patched system and re-verify.",
    }
    if missing or bad or extra:
        recovery["failed_files"] = sorted(missing + bad + extra)
    checks.append(recovery)

    result = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    now_text = iso(clock.now())
    run_id = db.execute(
        "INSERT INTO restore_runs (kind, started_at, result, backup_age_hours, files_total,"
        " files_ok, exposed, details) VALUES ('verify', ?, ?, 0, ?, ?, 0, ?)",
        (now_text, result, files_total, files_ok, json.dumps(checks)))
    db.emit("restore.verify", subject=("restore_run", run_id), result=result,
            vulns_found=vulns_found, vulns_fixed=max(vulns_found - vulns_remaining, 0),
            vulns_remaining=vulns_remaining, files_ok=files_ok)
    return {
        "id": run_id,
        "kind": "verify",
        "started_at": now_text,
        "result": result,
        "simulated_backup": _is_demo_layout(config),
        "vulns_found": vulns_found,
        "vulns_fixed": max(vulns_found - vulns_remaining, 0),
        "vulns_remaining": vulns_remaining,
        "backup_vuln_files": backup_vuln_files,
        "recovery": {"files_total": files_total, "files_ok": files_ok,
                     "markers_in_recovered": len(rec_markers)},
        "checks": checks,
    }


def _is_demo_layout(config: Config) -> bool:
    from demo_backup import make
    return config.restore_backup_dir == make.BACKUP_DIR
