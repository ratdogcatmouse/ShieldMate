# ShieldMate: decisions and ownership

Resolves the 22 decisions in the Build Spec PDF. Anything marked **TEAM** can't be decided from the documents and needs a name or a time from you. Everything else is agreed here; change a row by editing it and the file it points to.

## Team and ownership

This replaces the owner letters in the Build Spec.

| Person | Owns |
|---|---|
| **Ishaan** (backend core) | `main.py`, `config.py`, `db.py`, `errors.py`, `clock.py`, `tests/conftest.py`, contract tests; routes `clinic`, `alerts`, `notifications`, `actions`, `demo`, `events`; `alerts/*`, `lessons/*`, `actions/propose.py`, `targets.py`, `timeout.py`; `ingest/source.py`, `ingest/replay.py`; `eventlog/*` (the frontend's `telemetry.js` is Abhiram's) |
| **Cetas** (backend features) | `drills/*`, `scenarios/*`, `restore/*`, `demo_backup/*`; routes `drills`, `restore`, `devices`. Takes over `lessons/*` if Ishaan falls behind |
| **Abhiram** (frontend) | all of `frontend/`, `start.sh`, `Makefile`, translations, the backup video |
| **Kishaann** (Wazuh) | `lab/*`, `actions/wazuh_client.py` (real client **and** `FakeWazuhClient`), `ingest/wazuh.py` |

Kishaann hands the fake client to Ishaan first, so the approval flow doesn't wait for the lab.

## The 22 decisions

| # | Decision | Value | Changed by editing |
|---|---|---|---|
| 1 | Prep before H0? | **TEAM**: ask the organisers today. If yes, Kishaann starts the lab and everyone writes data files now | n/a |
| 2 | H0 time, demo slot, presenter | **TEAM**: fix all three now. The presenter rehearses as Dr. Rao from H19 | n/a |
| 3 | Owner PIN | **Off for now.** Kept in the contract (`pin_required` 401, `pin_invalid` 403, `X-Owner-Pin`, `OWNER_PIN`, `BACKSTAGE_TOKEN`), unused while the env vars are empty | `.env` |
| 4 | Owner plays staff steps? | No. Owner answers owner options and advances | scenario files |
| 5 | Readiness report | Out. End screen is "Team result" | n/a |
| 6 | Rule 100201 in live mode | Replay only. Live scope is `BLOCK_IP` on rule 60204 | `lessons.json` |
| 7 | Block length and wait | 60 min block, 5 min wait. Lab test T5.06 uses a 2-minute expiry. On stage, show the tap path | `seed/clinic.json`, `WAZUH_AR_COMMAND` |
| 8 | Backup approver | Ravi | `seed/clinic.json` |
| 9 | Undo | **Off for now.** Card says "Lifts at …". `/status.undo_supported` is false. Adopt only if lab test T5.07 passes | `/status`, `WazuhClient.unblock_ip` |
| 10 | Active-response command | `netsh3600` bound to dummy rule 100999 | `WAZUH_AR_COMMAND` |
| 11 | "Never block" | The explicit list only: router, Wazuh server, ShieldMate laptop | `seed/clinic.json` |
| 12 | When is a block simulated | Per alert from `alerts.source`. A replayed alert is always simulated, even in live mode | n/a (safety rule) |
| 13 | Which agent gets the block | `devices.wazuh_agent_id` in the seed. **Kishaann writes the real lab ID** | `seed/clinic.json` |
| 14 | Phone reload mid-drill | Join is idempotent per `staff_id`; frontend keeps `player_id` in localStorage | n/a |
| 15 | Notification cursor | `since_id`, no `read_at` | n/a |
| 16 | Escalation target | `notifications.to_staff_id` | n/a |
| 17 | Refused block | Stored as status `refused` with `refused_reason` | n/a |
| 18 | Count on the first live card | Rule 60204's own definition (8 failures in 4 min), then grouping bumps it | `lessons.json` |
| 19 | Languages | Kannada and Hindi on the alert card only, English fallback per string. **TEAM**: name the fluent checker | `lessons.json` |
| 20 | Scenario file name | `ransomware_clinic.json` | n/a |
| 21 | Network | Laptop hotspot; test at H2 with the internet unplugged; fallback is a travel router | n/a |
| 22 | Stage time for the live scene | **Live scene wins.** The AI toggle ships with fallback wording only and stays off on stage (`AI_REWORD=0`) | `.env` |

Also adopted from the spec's "Proposed" items: `GET /status`, the `heads_up` severity, `when_down` on devices, the error-code table and the 422 → `invalid_request` override.

## Where I departed from the spec text

These are small calls made while writing the frozen files. Reverse any of them by editing the file named.

- **Password-guessing alerts have `drill_scenario: null`** (`lessons.json`). The spec's example showed `"password_guessing"`, but that scenario is "not playable", so "Practise this with the team" would have started a drill that wasn't built to be presented. Set it back once the second drill is polished.
- **`devices.when_down` is a column** in `schema.sql`. The spec's seed has it but its table didn't, and the impact meter needs it.
- **Replay counts use `failures`**, not `count`, in `replay/alerts.json` (kept unchanged from the design). The normaliser must map `shieldmate.failures` to `counts.count`.
- **The owner's 60204 card has one step** ("Review the block request, or call your IT contact") instead of the spec's empty `steps: []`, so the card isn't blank when `ACTIONS` is off.
- **Billing gets the 60204 card** (same wording as front desk), so Ravi's phone shows it too.
- **`PUT /clinic/standing-rule` returns the `clinic` object** (`ClinicOut`), reading "the clinic object from GET /clinic" literally.
- **`RestoreCheck.failed_files` is optional**: the spec says it appears on the integrity check only, which conflicts with "every field is always present".
- **Draft wording to review:** owner and billing text for rule 60204 and all text for rule 100201 in `lessons.json`. The design only specified the front-desk card.
- **An event log was added after the freeze** (`backend/eventlog/`), recording everything that happens (user actions, alerts, actions, drills, restore checks, resets, errors, background loops) for later analysis. Four calls came with it:
  - **Its own SQLite file**, `backend/shieldmate-events.db` (beside `DB_PATH`; `EVENTS_DB_PATH` moves it), with one `events` table. `schema.sql` keeps its ten tables, and Reset never wipes the log: it starts a new `epoch` instead, because alert and action ids restart from 1.
  - **One new route, `POST /events`** (`contract.py` `EventsRequest`/`EventsAccepted`, `fixtures/events_accepted.json`), for the phones' UI events. This is a contract change, so the four owners need to agree to it.
  - **`EVENT_LOG` defaults on**, unlike the other flags, because it is the app's record rather than a feature. `EVENT_LOG=0` turns it off, and `/events` then answers `not_enabled`.
  - **Payloads hold ids, enums, counts and durations only**, from a per-type key list in `eventlog/catalogue.py`. Never logged: log text (`log_fields`/`raw`), notification text, reword output, staff names, PINs, tokens, request bodies or Wazuh responses. Refusals are logged as a code (`never_block`, `invalid_ipv4`, …), because the reason text quotes the untrusted IP.

## Still needs a human

- Seed values for live mode: `never_block` IPs and `wazuh_agent_id` must be replaced with the lab's real addresses and IDs (Kishaann). The attacker's IP must not be on `never_block`.
- Kannada and Hindi text (`translations` is empty, so cards fall back to English).
- CERT-In and DPDP feedback lines in `ransomware_clinic.json` step s4, and the `detail`/`fix` wording of the restore check, checked against the official texts.
- The IT contact number is a placeholder; keep it obviously fake on stage.

## Changing things later

| To change… | Edit… |
|---|---|
| Turn live mode, approvals or AI reword on or off | `ALERT_SOURCE`, `ACTIONS`, `AI_REWORD` in `backend/.env` |
| Add the owner PIN | set `OWNER_PIN` and `BACKSTAGE_TOKEN`; no route changes |
| Add Undo | make the unblock script work on the VM, then flip `undo_supported`; the route and error code already exist |
| Block length, wait time, backup approver, never-block list | `backend/seed/clinic.json` |
| Card wording, proposed action, add a rule | `backend/lessons/lessons.json` |
| Add a drill | a new file in `backend/scenarios/` in the same format |
| Any route or field | `backend/contract.py` **and** its fixture, with all four owners agreeing |
| Log a new kind of event | add it to `backend/eventlog/catalogue.py` and call `db.emit(...)` where it happens; a new `ui.*` type also goes in `contract.ClientEventType` |
| Turn the event log off, move it, or include the 2 s polls | `EVENT_LOG`, `EVENTS_DB_PATH`, `EVENT_LOG_READS` in `backend/.env` |
