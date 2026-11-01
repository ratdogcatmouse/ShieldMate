-- ShieldMate schema: eleven tables, live-mode columns included from H0 (T0.01).
-- Setup tables are re-seeded from seed/clinic.json on every reset;
-- runtime tables are emptied. "-- proposed (n)" marks Build Spec decision n.
-- "-- v2" marks the contract v2 additions (step ticking, "That was me", the IT loop).
-- user_version must match db.SCHEMA_VERSION: an older file is rebuilt at start-up.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 4;

-- setup (re-seeded on every reset)

CREATE TABLE staff (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('front_desk','billing','owner')),
  can_restore_backups INTEGER NOT NULL DEFAULT 0,
  can_approve_downtime INTEGER NOT NULL DEFAULT 0,
  is_backup_approver INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE clinic (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  backup_age_limit_hours INTEGER NOT NULL,
  it_contact_name TEXT NOT NULL,
  it_contact_phone TEXT NOT NULL,
  standing_rule_block_ip INTEGER NOT NULL DEFAULT 0,
  standing_rule_set_by INTEGER REFERENCES staff(id),
  standing_rule_set_at TEXT,
  approval_timeout_minutes INTEGER NOT NULL DEFAULT 5,
  block_minutes INTEGER NOT NULL DEFAULT 60,
  never_block TEXT NOT NULL DEFAULT '[]',         -- JSON list of {ip, label}
  reset_id TEXT NOT NULL DEFAULT ''               -- new random hex on every seed; browsers clear their demo state when it changes
);

CREATE TABLE devices (
  id INTEGER PRIMARY KEY,
  agent_name TEXT NOT NULL UNIQUE,
  wazuh_agent_id TEXT,                            -- proposed (13)
  location TEXT NOT NULL,
  services TEXT NOT NULL DEFAULT '[]',            -- JSON list of service keys
  when_down TEXT NOT NULL DEFAULT '{}',           -- JSON {service: note} for the impact meter
  status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','under_attack','protected')),
  status_changed_at TEXT
);

-- runtime (emptied on reset)

CREATE TABLE alerts (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL CHECK (source IN ('replay','wazuh')),   -- proposed (12)
  external_id TEXT UNIQUE,                        -- proposed: indexer _id, dedupes live polling
  rule_id TEXT NOT NULL,
  level INTEGER NOT NULL,
  agent_name TEXT NOT NULL,
  group_key TEXT NOT NULL,                        -- rule_id + ':' + agent_name
  count INTEGER NOT NULL DEFAULT 1,
  lesson_id TEXT,                                 -- NULL when filtered for no lesson
  status TEXT NOT NULL CHECK (status IN ('new','done','filtered','mine')),
  log_fields TEXT NOT NULL DEFAULT '{}',          -- JSON, verbatim strings
  raw TEXT NOT NULL,                              -- JSON, the original alert
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  done_by INTEGER REFERENCES staff(id),
  done_at TEXT,                                   -- v2
  mine_by INTEGER REFERENCES staff(id),           -- v2: "That was me"
  mine_at TEXT,                                   -- v2
  reopened INTEGER NOT NULL DEFAULT 0,            -- v2: came back after "That was me"
  it_received_at TEXT,                            -- v2: the IT loop (alerts/it.py)
  it_resolved_at TEXT,
  it_resolved_note TEXT,
  it_sent_back_at TEXT,
  it_sent_back_note TEXT,
  closed_at TEXT,                                 -- v2: the owner confirmed IT's fix
  closed_by INTEGER REFERENCES staff(id)
);

-- v2: ticked card steps, one row per alert and action ID (shared across roles).
CREATE TABLE alert_steps (
  alert_id INTEGER NOT NULL REFERENCES alerts(id),
  action TEXT NOT NULL,
  done_by INTEGER NOT NULL REFERENCES staff(id),
  done_at TEXT NOT NULL,
  PRIMARY KEY (alert_id, action)
);

-- v2: the incident's IT history. by_staff_id NULL = the clinic's IT contact.
CREATE TABLE alert_it_log (
  id INTEGER PRIMARY KEY,
  alert_id INTEGER NOT NULL REFERENCES alerts(id),
  at TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('called','received','note','resolved','confirmed','sent_back')),
  by_staff_id INTEGER REFERENCES staff(id),
  note TEXT
);

CREATE TABLE actions (
  id INTEGER PRIMARY KEY,
  alert_id INTEGER NOT NULL REFERENCES alerts(id),
  action_id TEXT NOT NULL CHECK (action_id = 'BLOCK_IP'),
  target_ip TEXT,
  agent_name TEXT NOT NULL,
  simulated INTEGER NOT NULL,                     -- 1 when the alert came from replay
  status TEXT NOT NULL CHECK (status IN
    ('proposed','approved','declined','executed','failed','expired','undone','refused','withdrawn')),
  refused_reason TEXT,                            -- proposed (17)
  decided_by INTEGER REFERENCES staff(id),
  decided_via TEXT CHECK (decided_via IN ('tap','standing_rule')),
  proposed_at TEXT NOT NULL,
  decided_at TEXT,
  expires_at TEXT,
  wazuh_response TEXT                             -- JSON, never returned by the API
);

CREATE TABLE notifications (
  id INTEGER PRIMARY KEY,
  alert_id INTEGER REFERENCES alerts(id),
  action_row_id INTEGER REFERENCES actions(id),   -- proposed: standing-rule and escalation notes
  from_staff_id INTEGER REFERENCES staff(id),
  to_role TEXT CHECK (to_role IN ('front_desk','billing','owner')),
  to_staff_id INTEGER REFERENCES staff(id),       -- proposed (16)
  -- v3: 'attack' = a new alert card; the route attaches a quick_action button to it
  kind TEXT NOT NULL DEFAULT 'info' CHECK (kind IN ('info','attack')),
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE drills (
  code TEXT PRIMARY KEY,                          -- 4 digits, unique among open drills
  scenario_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('lobby','open','review','finished')),
  step_index INTEGER NOT NULL DEFAULT -1,         -- -1 in lobby
  step_opened_at TEXT,
  host_staff_id INTEGER NOT NULL REFERENCES staff(id),
  source_alert_id INTEGER REFERENCES alerts(id),  -- proposed: "Practise this with the team"
  created_at TEXT NOT NULL
);

CREATE TABLE drill_players (
  id INTEGER PRIMARY KEY,
  drill_code TEXT NOT NULL REFERENCES drills(code),
  staff_id INTEGER NOT NULL REFERENCES staff(id),
  joined_at TEXT NOT NULL,
  UNIQUE (drill_code, staff_id)                   -- proposed (14): rejoin = same player
);

CREATE TABLE drill_answers (
  drill_code TEXT NOT NULL REFERENCES drills(code),
  player_id INTEGER NOT NULL REFERENCES drill_players(id),
  step_id TEXT NOT NULL,
  option_id TEXT NOT NULL,
  action_ids TEXT NOT NULL DEFAULT '[]',
  correct INTEGER NOT NULL,
  answered_at TEXT NOT NULL,
  PRIMARY KEY (drill_code, player_id, step_id)    -- answer once (T1.07)
);

CREATE TABLE restore_runs (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'check' CHECK (kind IN ('check','verify')),  -- verify = the recovery/patch test
  started_at TEXT NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('PASS','FAIL')),   -- NOT_TESTED is never stored
  backup_age_hours REAL NOT NULL,
  files_total INTEGER NOT NULL,
  files_ok INTEGER NOT NULL,
  exposed INTEGER NOT NULL,
  details TEXT NOT NULL                           -- JSON: checks[] as in the API
);

-- v3: restore-incident loop (restore/incident.py). A "not safe" check opens one; the IT
-- contact (clinic.it_contact_name, not a staff row) resolves it; the owner retests and
-- closes it when the next check is safe. One active (open/resolved) incident at a time.
CREATE TABLE restore_incidents (
  id INTEGER PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('open','resolved','closed')),
  last_result TEXT NOT NULL CHECK (last_result IN ('PASS','FAIL')),
  fix_steps TEXT NOT NULL DEFAULT '[]',          -- JSON list: the actionable steps for IT (from the failed checks)
  last_run_id INTEGER,                            -- the restore_runs row that set last_result
  it_resolved_at TEXT,
  it_resolved_note TEXT,
  it_sent_back_at TEXT,                           -- sent back to IT (owner declined, or a retest failed)
  it_sent_back_note TEXT,
  closed_at TEXT,
  closed_by INTEGER REFERENCES staff(id),
  created_at TEXT NOT NULL
);

-- Attack simulation (roadmap T8): one row per in-app attack-script run. The simulator is
-- the only writer; /demo/reset clears it like every other runtime table.
CREATE TABLE sim_runs (
  id INTEGER PRIMARY KEY,
  script_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running','contained','spread','stopped','expired')),
  outcome_reason TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT
);
