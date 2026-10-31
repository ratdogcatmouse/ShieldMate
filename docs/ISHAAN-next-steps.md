# Ishaan: wiring the 100201 auto-backup (one line, plus a smoke check)

Context: the attack-notification feature is live (`notify.attack` in the pipeline's
`created` branch). The last missing piece of the plan is the **auto-snapshot**: when an
encryption (100201) card is created, the compromised directory gets backed up
automatically instead of only on button press. Cetas's side is built and pushed
(`2ad86fb`); only your two-line call is left.

## The call

`alerts/pipeline.py`, inside `process()`'s `created` branch — right next to your existing
`notify.attack(...)` call:

```python
# An encryption card means a compromised state: back it up automatically so
# POST /restore/verify has something real to test. No-op on a real backup layout.
if alert.rule_id == "100201":
    from restore import verify
    verify.auto_snapshot(db, clock, config)
```

Notes:
- `auto_snapshot(db, clock, config) -> dict | None` is pipeline-safe by design: the demo
  layout snapshots `demo_backup/compromised/` into `restore_sandbox/snapshot/` and emits a
  `restore.snapshot` event; any real backup layout (`RESTORE_BACKUP_DIR` pointed elsewhere)
  returns `None` quietly; a broken layout can't crash the pipeline (it swallows and
  returns `None`).
- Only 100201 triggers it — password storms (60204/60106/61320) are a threat at the door,
  not data loss, so no snapshot.
- The event-log type `restore.snapshot` already exists in `eventlog/catalogue.py`.

## Smoke check

1. Start the demo layout (`python start.ps1` or the venv equivalent; `ACTIONS=1`).
2. Reset, then create a 100201 card: `POST /api/demo/replay/ransomware`
   (or sim: `POST /api/demo/simulate/ransom_wave` with the phase advanced).
3. Assert:
   - `backend/restore_sandbox/snapshot/` exists with 50 files,
   - a `restore.snapshot` row landed in the event log
     (`make events` or the events CLI in `Makefile`),
   - `POST /api/restore/verify` still returns its normal story (snapshot/update/recovery).
4. `python -m pytest tests/ -q` green.

## What's already here (don't rebuild)

- `restore/verify.py::auto_snapshot` / `snapshot_only` / `run_verify` (Cetas)
- `POST /restore/verify` route + `RestoreVerifyResult` contract + fixture (Cetas)
- `demo_backup/compromised/`, `patched/`, `vuln_markers.json` generation on reset (Cetas)
- `notifications.kind` + `quick_action` + `notify.attack` (Ishaan, already merged)
