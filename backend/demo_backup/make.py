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

Content is generated from a fixed seed, so the hashes are identical on every machine
("works on my laptop" means the same thing on the demo laptop). ``db.reset`` calls
``ensure(force=True)`` so a fresh reset always regenerates both folders.

The two on-disk folders are gitignored; they are generated artifacts.
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
ORIGINALS_DIR = BACKEND_DIR / "demo_backup" / "originals"
BACKUP_DIR = BACKEND_DIR / "demo_backup" / "backup"

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
          good: bool = False, now_text: str | None = None) -> dict:
    """(Re)generate both folders from scratch.

    ``good=True`` builds the test-only passing backup (T1.13): same 50 files, no
    altered files, ``last_backup_at = now`` and ``always_connected: false``.
    ``now_text`` pins the "current time" so tests get a stable, clock-independent build.
    """
    now_text = now_text or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for base in (originals_dir, backup_dir):
        shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True)

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
    return manifest


def _shift(now_text: str, days: int) -> str:
    """Move an ISO instant by whole days (the generator has no Clock of its own)."""
    dt = datetime.fromisoformat(now_text.replace("Z", "+00:00")) + timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure(force: bool = False) -> None:
    """Called by ``db.reset`` (force=True): rebuild the demo faults so every demo
    run starts from the same 50 files, 2 altered, 9 days old, always connected."""
    if force or not (ORIGINALS_DIR / "manifest.json").is_file() \
            or not (BACKUP_DIR / "backup_meta.json").is_file():
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
