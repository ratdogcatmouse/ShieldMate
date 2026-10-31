-- ShieldMate schema: ten tables, live-mode columns included from H0 (T0.01).
-- Setup tables are re-seeded from seed/clinic.json on every reset;
-- runtime tables are emptied. "-- proposed (n)" marks Build Spec decision n.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

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
  never_block TEXT NOT NULL DEFAULT '[]'          -- JSON list of {ip, label}
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
  status TEXT NOT NULL CHECK (status IN ('new','done','filtered')),
  log_fields TEXT NOT NULL DEFAULT '{}',          -- JSON, verbatim strings
  raw TEXT NOT NULL,                              -- JSON, the original alert
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  done_by INTEGER REFERENCES staff(id)
);

CREATE TABLE actions (
  id INTEGER PRIMARY KEY,
  alert_id INTEGER NOT NULL REFERENCES alerts(id),
  action_id TEXT NOT NULL CHECK (action_id = 'BLOCK_IP'),
  target_ip TEXT,
  agent_name TEXT NOT NULL,
  simulated INTEGER NOT NULL,                     -- 1 when the alert came from replay
  status TEXT NOT NULL CHECK (status IN
    ('proposed','approved','declined','executed','failed','expired','undone','refused')),
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
  started_at TEXT NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('PASS','FAIL')),   -- NOT_TESTED is never stored
  backup_age_hours REAL NOT NULL,
  files_total INTEGER NOT NULL,
  files_ok INTEGER NOT NULL,
  exposed INTEGER NOT NULL,
  details TEXT NOT NULL                           -- JSON: checks[] as in the API
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
