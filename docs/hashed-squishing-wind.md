# ShieldMate — Backend Build Plan (2-person split, build against the frozen contract)

## Context

The `dev` branch just got the team's pre-H0 work: the API contract, schema, and all
demo data are **frozen and committed**. This plan fills in **only the empty app code**
(36 `backend/*.py` files, 2 test stubs, `requirements.txt`) — **no new/renamed/removed
files or directories**, and nothing outside `backend/`.

**Source of truth, in order:** `docs/DECISIONS.md` (wins on conflicts, per `CLAUDE.md`)
> the four `docs/*.pdf` > `backend/contract.py`. The app code is the only thing still
empty; everything it consumes (`contract.py`, `schema.sql`, `seed/`, `lessons/`,
`scenarios/`, `replay/`, `fixtures/`) is already written and must be treated as fixed.

Scope (user decision): **increments 0–4 fully** (replay + drills + restore + reword
guard + simulated approval) **plus the increment-5 real httpx Wazuh client** (buildable;
gated behind `ALERT_SOURCE=wazuh`, off by default — replay/demo behavior untouched).
Test depth: **pragmatic** — the team's real Unit + API + Contract-level tests, cited by
their `T0–T6` IDs from the Testing Plan PDF (UI-flow / device / lab tests are out of
scope — they need phones and the Wazuh lab).

## The 2-person split (mirrors `docs/DECISIONS.md`'s two backend lanes)

`DECISIONS.md` maps backend files to **Ishaan (backend core)** and **Cetas (backend
features)**, with Kishaann owning the Wazuh client + live ingest. Folded to two people:

- **Lane 1 — "Backend core"** (Ishaan's files + Kishaan's Wazuh files): foundation
  (`config`, `db`, `errors`, `clock`, `main`, `conftest`), `alerts/*`, `ingest/*`,
  `lessons/*`, `actions/{propose,targets,timeout,wazuh_client}`, routes
  `clinic`/`alerts`/`notifications`/`actions`/`demo`. The increment-5 real Wazuh
  client + live ingest (`actions/wazuh_client.py` real client, `ingest/wazuh.py`)
  land here, but the **`FakeWazuhClient` ships with Lane 1** (Kishaan hands it over
  so the approval flow never waits for the lab).
- **Lane 2 — "Backend features"** (Cetas's files): `drills/*`, `scenarios/*`
  loader, `restore/checker.py`, `demo_backup/make.py`, routes `drills`/`restore`/
  `devices`.

> Note: I'm Cetas (the `dev` owner). In practice **I build both lanes**; the split
> exists so a teammate can take Lane 1 or Lane 2 in parallel. The seam between them:
> **Lane 2's `routes/devices.py` exports `set_device_status(db, agent_name, status,
> when)`**; Lane 1's `alerts/pipeline.py` (new 60204 → `under_attack`) and
> `actions/timeout.py` (executed → `protected`, expiry/done/undo → `ok`) call it.
> `alerts/pipeline.py` is the only writer of `alerts`; `drills/engine.py` the only
> writer of drill tables; `actions/*` the only writer of `actions`. Routes never do
> SQL. Nothing calls `datetime.now()` — everything takes the `Clock`.

## Foundation (Lane 1) — build against the frozen files

These are *new code*; the inputs they read are already committed:

- **`config.py`** — `Config` dataclass; loads `backend/.env` (tiny key=value parser,
  real env vars win); flags `"1"/"0"` → bool; paths/defaults exactly as
  `.env.example` (`ALERT_SOURCE=replay`, `AI_REWORD=0`, `ACTIONS=0`, `OWNER_PIN`/
  `BACKSTAGE_TOKEN` empty = PIN off, `WAZUH_AR_COMMAND=netsh3600`, …).
- **`clock.py`** — `Clock` protocol, `RealClock` (tz-aware UTC), `FakeClock`
  (start `2026-11-01T04:00:00Z`, matching the fixtures), `advance(s)`, plus
  `iso(dt)` → `"…Z"` and `parse_iso(s)`.
- **`errors.py`** — `ApiError(code, message, status)`; codes **exactly** `contract.
  ErrorCode`; body `{"error","message"}`; handlers for `ApiError`, 422 →
  `invalid_request`/400 (the spec's 422 override), catch-all → `internal_error`/500
  (details server-log only).
- **`db.py`** — one `sqlite3` conn (`check_same_thread=False`, `RLock`), per-conn
  WAL + `foreign_keys=ON`; run `schema.sql`; `load_seed()` from `seed/clinic.json`
  (incl. the `when_down` column); `reset(...)`: clear runtime tables children-first
  (`actions`,`drill_answers`,`drill_players`,`drills`,`restore_runs`,`notifications`,
  `alerts`), re-seed setup, regen synthetic backup via `demo_backup.make`, empty
  `restore_sandbox/`, reset replay cursors — idempotent (T0.07).
- **`main.py`** — `create_app(...)`: mount all routers under `/api`, error handlers,
  startup (DB+seed+backup ensure); on the running loop: 10 s `actions.timeout.run_once`,
  5 s `WazuhSource.next_batch` (only when `ALERT_SOURCE=wazuh`). Serve
  `frontend/dist` at `/` **only if it exists** (SPA fallback) — no frontend build here.
- **`tests/conftest.py`** — `sys.path` bootstrap to `backend/` (namespace packages,
  no `__init__.py` anywhere); fixtures: temp DB, `FakeClock`, `FakeWazuhClient`,
  `create_app`, `TestClient` (lifespan on); helpers `reset()`, `inject(type)`,
  `advance(s)`/`tick()` (run one 10 s timeout pass).
- **`requirements.txt`** (empty today) — pin installed versions: `fastapi==0.141.1`,
  `uvicorn==0.52.4`, `pydantic==2.13.4`, `httpx==0.28.1`, `pytest==9.0.1`.

## Lane 1 — alerts / lessons / actions / demo

- **`ingest/source.py`** — `AlertSource` protocol (`next_batch() -> list[RawAlert]`),
  `RawAlert` TypedDict `{source, external_id, alert, shieldmate}` per the spec.
- **`ingest/replay.py`** — `ReplaySource`: loads `replay/alerts.json`, per-type click
  cursors; `next_batch(type)` returns that click's records, stamps `timestamp` now,
  advances cursor; `reset_state()`; `ReplayExhausted` when no clicks left. (Reads the
  committed 5-record file — 60106 + 60204 for pguess click 1, 60204 for click 2, 550 +
  100201 for ransomware click 1 — matching `fixtures/demo_replay.json`.)
- **`ingest/wazuh.py`** (increment 5, gated) — `WazuhSource`: 5 s indexer `_search`
  poll (range `gte` last-seen, `terms` on seed agent names, size 100, TLS via
  `WAZUH_CA_CERT`), dedupe by `_id`→`external_id`, map to `RawAlert`
  (`shieldmate=None`, `source="wazuh"`), record last health snapshot for `/status`.
- **`alerts/normalise.py`** — `NormalisedAlert` dataclass + `normalise(raw, now)`;
  IP from `data.win.eventdata.ipAddress` → `source_ip`, `targetUserName` →
  `username_tried` (verbatim); `counts` maps **`shieldmate.failures` → `count`**,
  plus `window_minutes`/`files_renamed` (DECISIONS departure #3); else lesson
  `count_defaults`.
- **`alerts/filter.py`** — `should_filter(na, lesson)`: level `< 7` **or** no lesson →
  filtered (T2.01). 60106(level 3) and 550(level 7, no lesson) both filter; 60204/
  100201 don't.
- **`alerts/group.py`** — `find_group(db, na, now)`: same `group_key`
  (`rule_id:agent_name`), `last_seen` within 10 min, status `new` → `count += 1`,
  bump `last_seen`; known `external_id` reprocessed → no-op.
- **`alerts/pipeline.py`** — `process(alert, db, clock)` → created|grouped|filtered
  (the only `alerts` writer); on **created**: if `ACTIONS` on and lesson
  `proposed_action == "BLOCK_IP"` → `actions.propose`; if rule 60204 →
  `set_device_status(under_attack)`.
- **`lessons/engine.py`** — load/validate `lessons.json` (T0.06), index by rule_id;
  `card_for(alert, lesson, role, lang)` fills placeholders from counts, picks role
  text (missing role → card omitted), per-string English fallback for `translations`
  (currently empty). Reads the committed `lessons.json` (60204 has front_desk, billing,
  owner; 100201 owner-only).
- **`lessons/reword.py` + `providers.py`** — guard + providers. `RewordProvider`
  (`reword(headline, why) -> (h, w)`), `NoneProvider` (raises `NotConfigured` →
  fallback). Output checks (T3.02): ≤200 chars each, every number preserved, no new
  digit runs, no links → else `fallback_reword` `source:"fallback"`. Input is always
  exactly the two filled strings (T3.01 — the poisoned `username_tried` never reaches
  it).
- **`actions/targets.py`** — `check_target(ip, never_block) -> (ok, reason)`: strict
  IPv4; never-block match → `"192.168.1.1 is the clinic router"` style (matches
  `fixtures/action_refused.json`); refuses IPv6/empty/invalid (T4.03).
- **`actions/propose.py`** — on new alert, `ACTIONS` on: insert `actions` row
  (`proposed`, `expires_at = now + approval_timeout_minutes`, `simulated =
  alert.source == "replay"` (decision 12)); target invalid/never-block → `refused`
  + `refused_reason` (decision 17). Ransomware (100201, `proposed_action null`)
  proposes **nothing** (T4.02).
- **`actions/timeout.py`** — `run_once(db, clock, config, client)` (the 10 s task):
  proposed past `expires_at` → standing rule on: execute (`decided_via
  "standing_rule"`, `executed`, `expires_at = now + block_minutes`, device
  `protected`, owner notif "Blocked under your standing rule."); off: stay + notify
  backup approver once with the IT contact number. Executed past `expires_at` →
  `expired`, device `ok` (T4.06–T4.08).
- **`actions/wazuh_client.py`** — `WazuhClient` protocol (`block_ip`/`unblock_ip`/
  `health`), `FakeWazuhClient` (records `.calls`, sends nothing), and the
  **increment-5 `RealWazuhClient`** (httpx, `WAZUH_TIMEOUT_SECONDS`): JWT
  authenticate + re-login on 401, `PUT /active-response?agents_list=<id>`
  `{"command": WAZUH_AR_COMMAND, "alert":{"data":{"srcip": ip}}}`, `GET /agents?…
  &select=status` for health. Credentials never returned (T5.10).
- **`routes/clinic.py`** — `GET /clinic` (incl. computed `single_point_of_failure`
  from staff flags), `PUT /clinic/standing-rule` (**returns `ClinicOut`**, ACTIONS),
  `GET /status` (flags, `alert_source`, `undo_supported`, `server_time`; `wazuh`
  null in replay).
- **`routes/alerts.py`** — `GET /alerts?role=&lang=` (non-filtered, newest
  `last_seen` first, per-role card, `hidden_count`); `POST /alerts/{id}/done`
  (idempotent; one owner notification; 60204 + no active block → device `ok`);
  `POST /alerts/{id}/reword` (AI_REWORD flag else `not_enabled` 404).
- **`routes/notifications.py`** — `GET /notifications?role=&staff_id=&since_id=`
  (to-role OR to-staff, id > since_id, oldest first, `last_id`).
- **`routes/actions.py`** — `GET /actions?status=` (`label`, `seconds_left` while
  proposed, `on_timeout`, `undo_available`; never `wazuh_response`); `/approve`
  (re-check target → `target_refused`; simulated → `executed` now, no client call;
  live → client call, fail → `failed` + `wazuh_unavailable` 502); `/decline`;
  `/undo` (409 unless `undo_supported` + executed). All `not_enabled` while ACTIONS
  off (T4.13).
- **`routes/demo.py`** — `POST /demo/replay/{alert_type}` (inject next click through
  the pipeline; `injected/cards_created/grouped/filtered/clicks_left`; unknown type
  → `invalid_request`, exhausted → `replay_exhausted` 409) and `POST /demo/reset`.

## Lane 2 — drills / restore / devices / demo backup

- **`drills/models.py`** — scenario dataclasses + loader/validator (T0.04/T0.05
  rules: unique `step_id`, phase from enum, exactly one `correct:true` per role with
  options, action IDs from the vocabulary, `triggers` only `"restore_check"`, device
  names in seed). Reads the committed `scenarios/ransomware_clinic.json` (4 steps) and
  `password_guessing.json` (2 steps, "format proof").
- **`drills/engine.py`** — owns all drill writes: create (unique 4-digit code among
  open drills; host auto-joined → `player_id`; `invalid_request` for unknown
  scenario), join (idempotent per staff, decision 14; lobby/open only), state
  machine (`lobby → open → review → open … → finished`; host-only advance, else
  `not_host`), answers (once; `invalid_option`/`already_answered`/`step_closed`;
  step auto-closes when all has-options players answered, T1.10; host advance closes
  early, non-answers = wrong), `restore_check_available` when the host picks a
  `restore_check` option (T1.16). The view is assembled to **match the committed
  `drill_view*.json` fixtures exactly** (options filtered by viewer role;
  `correct`/`feedback`/`actions` only after that player answered; `waiting_message`
  when a role has no options; `review.answers` with `option_text`/`correct`).
- **`drills/scoring.py`** — pure: per-player per-phase `correct/total`, team total,
  `missed_actions` = union of the correct option's `action_ids` over every step the
  player got wrong or didn't answer, deduped in step order. Reproduce
  `fixtures/drill_view_finished.json` (Ravi misses s1+s2 → `ISOLATE_NETWORK,
  CALL_SAVED_IT, NOTIFY_OWNER`, team 8/10). `results` only when finished;
  `restore` = latest run result or null.
- **`drills/impact.py`** — pure join of a step's `devices` states with the DB's
  `services` + `when_down` (T2.06; design Appendix A table): `ok` → services `ok`;
  `infected`/`isolated`/`encrypting`/`encrypted` → a service is `moved` iff it has a
  `when_down` note (note verbatim, e.g. "Check-in moves to the billing PC"), other
  services `down`, first `unavailable` (matches the `encrypting` FILE-SERVER row:
  down, down, unavailable). No simulation — lookup only.
- **`routes/drills.py`** — the five `/drills` routes, bodies per fixtures.
- **`restore/checker.py`** — `run_check(db, clock, config)`: copy `RESTORE_
  BACKUP_DIR` into `RESTORE_SANDBOX_DIR` (the only folder it writes, T1.14), then
  **freshness** (`backup_meta.last_backup_at` age vs `clinic.backup_age_limit_hours`),
  **integrity** (sha256 each sandbox file vs `RESTORE_MANIFEST`; `failed_files` on
  this check only — optional per DECISIONS), **exposure** (`always_connected`).
  `result=PASS` only if all three pass; store a `restore_runs` row (`details` = the
  checks JSON); `simulated_backup` = true unless the env points at a real folder.
  Reproduce `fixtures/restore_run.json` (48/50, 216 h, exposed → FAIL).
- **`routes/restore.py`** — `POST /restore/run` (owner, sync) and `GET
  /restore/latest` (the null `NOT_TESTED` shape, `fixtures/
  restore_latest_untested.json`, T1.15).
- **`routes/devices.py`** — `GET /devices` (spec shape; per-device `block` from an
  unexpired executed action; `not_enabled` while ACTIONS off) + the exported
  `set_device_status(db, agent_name, status, when)` helper the alerts lane calls.
- **`demo_backup/make.py`** — deterministic (fixed seed, machine-independent
  hashes): 50 small `.txt` files across `invoices/`/`letters/`/`appointments/` in
  `originals/` + `manifest.json {generated_at, files:{relpath: sha256}}`;
  `backup/` = copy with **exactly** `invoices/invoice_017.txt` +
  `letters/letter_032.txt` altered + `backup_meta.json {last_backup_at: now-9d,
  always_connected: true}` → checker gives 48/50 / 216 h / FAIL (T0.06, T1.12).
  `--good` variant → all-PASS (T1.13). `ensure(force)` called on reset.

## Tests (pragmatic: Unit + API + Contract, cited by T-ID)

- **`tests/contract/`** (new modules): validate every `ROUTES` response against
  `contract.py` and the matching `fixtures/*.json`; all 21 routes return 200 with
  contract-valid bodies (T0.02).
- **`tests/unit/`**: fill existing `test_filter.py` (T2.01), `test_engine.py`
  (drill state machine T1.06, answer-once T1.07, step-closes T1.10) + add
  `test_group.py`, `test_pipeline.py`, `test_reword.py` (T3.01/T3.02 spy),
  `test_targets.py` (T4.03), `test_timeout.py` (T4.06–T4.08 via `clock.advance`),
  `test_scoring.py` (T1.11/T2.07), `test_impact.py` (T2.06), `test_models.py`
  (T0.04), `test_restore.py` (T1.12/T1.13/T1.14), `test_backup.py` (T0.06),
  `test_replay.py` (T0.05 click/exhaustion/reset).
- **`tests/api/`** (new modules): full demo story (T1.01–T1.05, T1.15, T1.16);
  reset idempotency (T0.07); error shape (T0.03); ACTIONS-off `not_enabled` (T4.13);
  approval flow with `FakeWazuhClient.calls == []` (T4.03/T4.11); rejoin idempotent
  (T2.09-ish); single-point-of-failure (T2.08).

Run: `cd backend && python -m pytest -q`. (`Makefile`/`start.sh`/`README.md` are
empty top-level files in Abhiram's lane — **out of scope**; `make test` works once
someone fills the Makefile.)

## Execution order

1. **Foundation** (`config`,`db`,`errors`,`clock`,`main`,`conftest`,
   `requirements.txt`) → app boots; `GET /api/clinic` + `POST /api/demo/reset` green.
2. **Lane 1**: ingest/replay → alerts pipeline + lessons engine → routes
   alerts/notifications/clinic/status → actions (targets/propose/timeout/fake+real
   client) + routes actions/demo → unit + contract + api green.
3. **Lane 2**: drills models+engine → scoring/impact + routes drills → demo_backup +
   restore checker + routes restore/devices → green.
4. **Cross-lane**: pipeline→device-status, standing-rule→notification, and the full
   demo-story API test; final `pytest -q`.

## Verification

- `cd ShieldMate/backend && python -m pytest -q` — green (Unit+API+Contract gates).
- Boot: `python -m uvicorn main:app --port 8000`, then `POST /api/demo/reset` →
  `POST /api/demo/replay/password_guessing` → `GET "/api/alerts?role=front_desk"`
  → `POST /api/drills` → one answer → `POST /api/restore/run`; each matches its
  `fixtures/*.json`.
- Flags off (default `.env`): `/api/actions`, `/api/devices` → 404 `not_enabled`;
  reword → 404; the replay/demo story still runs simulated end to end.

## Open call (non-blocking)

How to fold **Kishaann's Wazuh files** (`actions/wazuh_client.py` real client +
`ingest/wazuh.py`) into exactly two people. Default: **Lane 1** (core/live), shipping
the `FakeWazuhClient` with Lane 1 so the approval flow never waits on the lab; the
real client + live ingest stay gated behind `ALERT_SOURCE=wazuh`. Say the word if you
want them in a separate third lane instead.
