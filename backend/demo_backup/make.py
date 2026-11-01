"""The synthetic demo backup generator (T0.06, and the faults the demo story needs).

Demo story: the clinic's backup is old, slightly corrupt and always plugged in, so the
restore check shows three real faults to discuss. This generator plants exactly those
faults, deterministically, so the demo always starts from the same state:

- ``originals/`` holds 50 harmless sample files plus ``manifest.json`` with each file's
  SHA-256 (the "known good" hashes the checker compares against).
- ``backup/`` holds a copy of the same 50 files with **exactly two altered**
  (``invoice_017`` and ``letter_032``, the integrity failures), plus
  ``backup_meta.json`` saying the backup is 9 days old and the drive is always
  connected (the freshness and exposure failures).

The verify story (``restore/verify.py``) adds two more trees, generated the same way:

- ``compromised/`` - the clinic's *live* records directory after an attack: the same 50
  files, but three carry literal **vulnerability markers** (old SQL-injection string,
  an MD5 password hash, a legacy TLS cipher).
- ``patched/`` - the IT update: only those three files, rewritten clean.

Content is generated from a fixed seed, so the hashes are identical on every machine
("works on my laptop" means the same thing on the demo laptop). ``db.reset`` calls
``ensure(force=True)`` so a fresh reset always regenerates all the folders.

The on-disk folders are gitignored; they are generated artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = BACKEND_DIR / "demo_backup"
ORIGINALS_DIR = BASE_DIR / "originals"
BACKUP_DIR = BASE_DIR / "backup"
NEW_BACKUP_DIR = BASE_DIR / "backup_new"   # IT's repaired backup - a separate, clean tree
COMPROMISED_DIR = BASE_DIR / "compromised"     # the live directory, mid-attack
PATCHED_DIR = BASE_DIR / "patched"             # the IT update (only the fixed files)
MARKERS_FILE = BASE_DIR / "vuln_markers.json"

# 50 files across the three clinic folders. The two deliberately-altered files below are
# named by fixtures/restore_run.json, so the paths must stay exactly these.
_NAMES = (
    [f"invoices/invoice_{i:03d}.txt" for i in range(1, 18)]      # 17 (incl. invoice_017)
    + [f"letters/letter_{i:03d}.txt" for i in range(1, 33)]      # 32 (incl. letter_032)
    + [f"appointments/appt_{i:03d}.txt" for i in range(1, 2)]    # 1
)
assert len(_NAMES) == 50, "the demo backup is defined as exactly 50 files"

ALTERED_FILES = {"invoices/invoice_017.txt", "letters/letter_032.txt"}

# Faults planted in the demo backup: 9 days old, drive always connected.
FAULT_AGE_DAYS = 9

# The verify story: which live files carry which vulnerability marker (literal strings -
# the scanner is a substring search, so the demo is deterministic and needs no runtime).
VULN_MARKERS = ["VULN-SQLI-001", "VULN-MD5-002", "VULN-TLS-LEGACY-003"]
COMPROMISED_FILES = {
    "invoices/invoice_005.txt": VULN_MARKERS[0],      # old, vulnerable query build
    "letters/letter_010.txt": VULN_MARKERS[1],        # passwords hashed with MD5
    "appointments/appt_001.txt": VULN_MARKERS[2],     # legacy TLS cipher in the exporter
}
assert len(COMPROMISED_FILES) == 3, "the verify demo story plants exactly three vulnerabilities"


def _content(rel: str, altered: bool = False) -> str:
    """Deterministic fake record text. ``random.Random(str)`` seeds from the string's
    SHA-512, so it is platform- and PYTHONHASHSEED-independent."""
    rng = random.Random("shieldmate:" + rel)
    words = ("clinic", "appointment", "invoice", "patient", "billing", "records",
             "followup", "lab", "referral", "payment")
    lines = [f"ShieldMate demo record: {rel}"]
    for _ in range(6):
        lines.append(" ".join(rng.choices(words, k=6)))
    if altered:
        # A corrupt byte: the file no longer hashes to the manifest's "original" hash.
        lines.append("## CORRUPTED BY DEMO FAULT")
    return "\n".join(lines) + "\n"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build(originals_dir: Path = ORIGINALS_DIR, backup_dir: Path = BACKUP_DIR,
          good: bool = False, now_text: str | None = None,
          compromised_dir: Path | None = None, patched_dir: Path | None = None,
          markers_path: Path | None = None) -> dict:
    """(Re)generate all demo folders from scratch.

    ``good=True`` builds the test-only passing backup (T1.13): same 50 files, no
    altered files, ``last_backup_at = now`` and ``always_connected: false``.
    ``now_text`` pins the "current time" so tests get a stable, clock-independent build.

    The verify-story trees are always regenerated (they are part of the same demo
    state). By default they live next to the backup folder (``<backup>/../compromised``,
    ``patched``, ``vuln_markers.json``), so a test build in a temp dir stays fully
    sandboxed; pass explicit paths to point elsewhere.
    """
    now_text = now_text or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = Path(backup_dir).parent
    compromised_dir = Path(compromised_dir) if compromised_dir else base / "compromised"
    patched_dir = Path(patched_dir) if patched_dir else base / "patched"
    markers_path = Path(markers_path) if markers_path else base / "vuln_markers.json"
    for dir_ in (originals_dir, backup_dir, compromised_dir, patched_dir):
        shutil.rmtree(dir_, ignore_errors=True)
        Path(dir_).mkdir(parents=True)
    # The old backup stays the baseline: a rebuild drops the repaired (new) backup too, so the
    # demo always restarts with the faulty backup as the only one on disk.
    shutil.rmtree(NEW_BACKUP_DIR, ignore_errors=True)

    # 1. The originals and their manifest (the expected hashes).
    manifest: dict[str, str] = {}
    for rel in _NAMES:
        # Write bytes, not text: on Windows write_text would translate the \n's to
        # \r\n and the checker's binary hash no longer matches the manifest's.
        target = Path(originals_dir) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_content(rel).encode("utf-8"))
        manifest[rel] = _sha256(_content(rel))
    (Path(originals_dir) / "manifest.json").write_text(
        json.dumps({"generated_at": now_text, "files": manifest}), encoding="utf-8")

    # 2. The backup: a copy, with the demo faults unless this is the "good" fixture.
    last_backup_at = now_text if good else _shift(now_text, days=-FAULT_AGE_DAYS)
    for rel in _NAMES:
        altered = not good and rel in ALTERED_FILES
        target = Path(backup_dir) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_content(rel, altered).encode("utf-8"))
    meta = {"last_backup_at": last_backup_at, "always_connected": not good}
    (Path(backup_dir) / "backup_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    # 3. The verify story: the compromised live directory, the clean IT patch, and the
    #    marker list the scanner reads (one file so generator and scanner can't drift).
    _build_verify_trees(compromised_dir, patched_dir, markers_path)
    return manifest


def _build_verify_trees(compromised_dir: Path, patched_dir: Path, markers_path: Path) -> None:
    """Compromised = the 50 originals, three with markers; patched = just those three, clean."""
    for rel in _NAMES:
        marker = COMPROMISED_FILES.get(rel)
        text = _content(rel)
        if marker:
            text += f"# VULNERABLE: {marker}\n"
        target = Path(compromised_dir) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        # The IT update rewrites only the vulnerable files, without the marker.
        if marker:
            clean = Path(patched_dir) / rel
            clean.parent.mkdir(parents=True, exist_ok=True)
            clean.write_bytes(_content(rel).encode("utf-8"))
    markers_path.write_text(json.dumps({"markers": VULN_MARKERS, "compromised_files": sorted(COMPROMISED_FILES)}),
                            encoding="utf-8")


def build_new(now_text: str | None = None, new_backup_dir: Path = NEW_BACKUP_DIR) -> None:
    """Build IT's repaired backup as a *separate* clean tree (``backup_new/``).

    The old faulty backup (``backup/``) is left in place as the baseline - the story is
    "back up the compromised thing, fix it, and keep the repaired copy alongside the old
    one." The clean tree's files hash to the originals' manifest and its meta says fresh +
    disconnected, so a check against it passes all three checks.
    """
    now_text = now_text or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    shutil.rmtree(new_backup_dir, ignore_errors=True)
    Path(new_backup_dir).mkdir(parents=True)
    for rel in _NAMES:
        target = new_backup_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_content(rel).encode("utf-8"))
    meta = {"last_backup_at": now_text, "always_connected": False}
    (new_backup_dir / "backup_meta.json").write_text(json.dumps(meta), encoding="utf-8")


def target_backup(config_restore_backup_dir: Path) -> Path:
    """Which backup a check should run against, in the demo layout: IT's repaired
    ``backup_new/`` when it exists, else the old ``backup/``. A real backup drive
    (anywhere but demo_backup/) is always checked as-is.
    """
    base = Path(config_restore_backup_dir).parent
    if base.name == "demo_backup" and (NEW_BACKUP_DIR / "backup_meta.json").is_file():
        return NEW_BACKUP_DIR
    return Path(config_restore_backup_dir)


def _shift(now_text: str, days: int) -> str:
    """Move an ISO instant by whole days (the generator has no Clock of its own)."""
    dt = datetime.fromisoformat(now_text.replace("Z", "+00:00")) + timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure(force: bool = False) -> None:
    """Called by ``db.reset`` (force=True): rebuild the demo state so every demo run
    starts from the same 50 files, 2 altered, 9 days old, always connected - and the
    verify story (compromised/patched trees + marker list) regenerates too."""
    if force or not (ORIGINALS_DIR / "manifest.json").is_file() \
            or not (BACKUP_DIR / "backup_meta.json").is_file() \
            or not (COMPROMISED_DIR / "invoices").is_dir() or not MARKERS_FILE.is_file():
        build()


def main() -> None:
    """Command-line convenience: ``python demo_backup/make.py [--good]`` regenerates in place."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--good", action="store_true",
                        help="build the test-only passing backup (no faults)")
    args = parser.parse_args()
    build(good=args.good)
    print(f"built {'good' if args.good else 'demo-fault'} backup at {BACKUP_DIR}")


if __name__ == "__main__":
    main()
