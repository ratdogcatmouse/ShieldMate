"""The restore check: does this backup actually come back intact, fresh and unexposed?

A real restore plus a real hash comparison - only the backup itself is synthetic
(see ``demo_backup/make.py``). The checker copies the backup into ``restore_sandbox/``
(the only folder it ever writes to, T1.14), hashes every file against the manifest,
and reports three checks, in the order a non-technical owner reads them:

- **freshness**  - is the backup younger than the clinic's limit?
- **integrity**  - do the restored files hash to their originals?
- **exposure**   - is the backup drive always attached to the (infected) server?

``result`` is PASS only when all three pass (T1.12, T1.13). The wording below is the
demo placeholder; someone checks the CERT-In/DPDP lines against the official texts.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from clock import Clock, iso, parse_iso
from config import Config
from db import Database

# Detail/fix wording (placeholder until the CERT-In/DPDP sign-off, see DECISIONS.md).
_FRESH_FIX = "Back up every day, and check that it ran."
_INTEGRITY_FIX = "Repair the backup and run this check again before trusting it."
_EXPOSURE_FIX = "Unplug the backup drive after each backup, or keep an offline copy."


def run(db: Database, clock: Clock, config: Config) -> dict:
    """Run the check now and store the result in ``restore_runs``. Synchronous: 50 small
    files take well under a second, so the owner's button returns the result inline."""
    now = clock.now()
    clinic = db.clinic()

    backup_meta = json.loads(Path(config.restore_backup_dir, "backup_meta.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path(config.restore_manifest).read_text(encoding="utf-8"))

    # 1. Copy the backup into the sandbox - the only place the checker writes (T1.14).
    sandbox = config.restore_sandbox_dir
    shutil.rmtree(sandbox, ignore_errors=True)
    shutil.copytree(config.restore_backup_dir, sandbox)

    checks: list[dict] = []

    # 2. Freshness: age the backup against the clinic's limit.
    age_hours = (now - parse_iso(backup_meta["last_backup_at"])).total_seconds() / 3600
    limit = clinic["backup_age_limit_hours"]
    fresh = age_hours <= limit
    days = int(age_hours // 24)
    checks.append({
        "check": "freshness", "passed": fresh,
        "detail": (f"Last backup was {days} days ago. Your limit is {limit} hours."
                   if not fresh else f"Last backup was {int(age_hours)} hours ago. Your limit is {limit} hours."),
        "fix": _FRESH_FIX,
    })

    # 3. Integrity: every file must hash to its original (the manifest's expected values).
    files = sorted(manifest["files"])
    failed = [rel for rel in files
              if _sha256(Path(sandbox, rel)) != manifest["files"][rel]]
    total, ok = len(files), len(files) - len(failed)
    integrity_check = {
        "check": "integrity", "passed": not failed,
        "detail": f"{ok} of {total} files restored exactly. {len(failed)} did not match."
        if failed else f"All {total} files restored exactly.",
        "fix": _INTEGRITY_FIX,
    }
    # failed_files appears on the integrity check only (DECISIONS.md departure).
    if failed:
        integrity_check["failed_files"] = failed
    checks.append(integrity_check)

    # 4. Exposure: a backup drive that is always attached can get encrypted with the server.
    exposed = bool(backup_meta.get("always_connected", False))
    checks.append({
        "check": "exposure", "passed": not exposed,
        "detail": "The backup drive is always connected to the server." if exposed
        else "The backup drive is disconnected after each backup.",
        "fix": _EXPOSURE_FIX,
    })

    result = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    details = json.dumps(checks)
    run_id = db.execute(
        "INSERT INTO restore_runs (started_at, result, backup_age_hours, files_total, files_ok, exposed, details)"
        " VALUES (?,?,?,?,?,?,?)",
        (iso(now), result, round(age_hours, 1), total, ok, int(exposed), details))
    return view(db, run_id, config)


def latest(db: Database, config: Config) -> dict:
    """The newest stored run, or the NOT_TESTED placeholder before the first run (T1.15)."""
    row = db.one("SELECT * FROM restore_runs ORDER BY id DESC LIMIT 1")
    if row is None:
        return {"id": None, "result": "NOT_TESTED", "simulated_backup": _is_simulated(config),
                "started_at": None, "backup_age_hours": None, "files_total": None,
                "files_ok": None, "exposed": None, "checks": []}
    return view(db, row["id"], config)


def view(db: Database, run_id: int, config: Config) -> dict:
    """One ``restore_runs`` row in the ``RestoreRun`` wire shape."""
    row = db.one("SELECT * FROM restore_runs WHERE id = ?", (run_id,))
    checks = json.loads(row["details"])
    for c in checks:
        c.setdefault("failed_files", None)   # the contract's one optional field
    exposed = bool(row["exposed"])
    return {
        "id": row["id"],
        "started_at": row["started_at"],
        "result": row["result"],
        "simulated_backup": _is_simulated(config),
        "backup_age_hours": row["backup_age_hours"],
        "files_total": row["files_total"],
        "files_ok": row["files_ok"],
        "exposed": exposed,
        "checks": checks,
    }


def _is_simulated(config: Config) -> bool:
    """True unless the env points at a real (non-demo) backup folder - drives the badge.

    The demo layout is ``<...>/demo_backup/backup``; pointing RESTORE_BACKUP_DIR at
    anything else means a genuine backup drive, which the badge must not call simulated.
    """
    return config.restore_backup_dir.parent.name == "demo_backup"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
