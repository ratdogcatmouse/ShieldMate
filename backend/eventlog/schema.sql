-- ShieldMate event log: an append-only record of everything that happens, kept for later
-- analysis. Its own SQLite file (not the ten-table schema.sql), so a demo reset never wipes it;
-- only `make clean-slate` (./start.sh --clean-slate) deletes the file.
-- Types and their data keys are listed in eventlog/catalogue.py.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,                           -- 'epoch': how many demo resets so far
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,                               -- ISO 8601 UTC 'Z', from the server Clock
  type TEXT NOT NULL,                             -- e.g. 'alert.created', 'ui.page_view'
  origin TEXT NOT NULL CHECK (origin IN ('server','client')),
  actor_staff_id INTEGER,                         -- NULL = the system, or nobody known
  actor_role TEXT,
  subject_type TEXT,                              -- alert | action | drill | restore_run | device | notification
  subject_id TEXT,
  request_id TEXT,                                -- ties request.completed to the events it caused
  session_id TEXT,                                -- one browser tab (frontend telemetry.js)
  run_id TEXT NOT NULL,                           -- one server process
  epoch INTEGER NOT NULL,                         -- ids restart after a reset; (epoch, subject) is unique
  data TEXT NOT NULL DEFAULT '{}',                -- JSON, keys from the catalogue only
  v INTEGER NOT NULL DEFAULT 1                    -- payload version
);

CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_type ON events(type);
CREATE INDEX IF NOT EXISTS events_subject ON events(epoch, subject_type, subject_id);
CREATE INDEX IF NOT EXISTS events_session ON events(session_id);
