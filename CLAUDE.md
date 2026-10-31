# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## State of the repo

This is mostly a scaffold: the app code (`*.py` modules, `frontend/`, `lab/`) is still **empty**. What *is* written and frozen is the contract and demo content, all validated against the Testing Plan's T0.04–T0.06 rules:

- [docs/DECISIONS.md](docs/DECISIONS.md) — the 22 pre-H0 decisions, **team ownership** (Ishaan: backend core; Cetas: drills/restore/devices; Abhiram: frontend; Kishaann: Wazuh lab and live mode), and where it departs from the spec. Read it before the PDFs; it wins on conflicts.
- `backend/contract.py` (Pydantic models and the 21-route `ROUTES` index), `backend/fixtures/*.json` (one stub body per route), `backend/schema.sql`, `backend/seed/clinic.json`, `backend/replay/alerts.json`, `backend/scenarios/*.json`, `backend/lessons/lessons.json`, `backend/.env.example`.

Owner PIN and Undo are deliberately off but kept in the contract. `lessons.json` has English only (Kannada/Hindi pending a fluent checker). `seed/clinic.json` IPs and agent IDs are placeholders until the Wazuh lab exists.

The original source documents are the four PDFs in `docs/`, which are not text-searchable from the shell (no `pdftotext`; extract with `pypdf` into the scratchpad if you need to re-read them):

- `ShieldMate — Build Spec (finalise before H0).pdf` — the API contract, data model, env flags, module interfaces, Wazuh lab settings. Items marked "Proposed" are resolved in DECISIONS.md.
- `ShieldMate Development Plan.pdf` — increments 0–6, owners, cut rules.
- `ShieldMate Testing Plan.pdf` — gate tests `T0.xx`–`T6.xx` (gate number = increment number).
- `ShieldMate design plan.pdf` — Software Design, with Appendix A (drill scenario) and Appendix B (replay alerts), which the spec says to use unchanged.

When implementing a file, read the matching section of the Build Spec first, and build route responses against `contract.py`. Don't invent routes, fields or error codes; the contract is meant to be frozen.

## What it is

ShieldMate turns Wazuh security alerts into plain-language, role-specific cards for non-technical clinic staff (Indian small-clinic setting: Sunrise Family Clinic, staff Meena / Ravi / Dr. Rao). It has three features: alert cards on phones, a role-split ransomware **drill** run on phones, and a **restore check** of a (synthetic) backup. An optional approval flow lets the owner approve a `BLOCK_IP` action on rule 60204. It was designed for a 24-hour hackathon build, and the demo runs on a laptop hotspot with two phones.

## Commands (planned, per the spec; none work until the files are filled in)

```
./start.sh                                   # npm ci + build frontend, then uvicorn on :8000, single worker, no --reload
make test                                    # cd backend && .venv/bin/pytest -q
cd backend && .venv/bin/pytest -q tests/unit/test_filter.py::test_name   # single test
make e2e                                     # cd frontend && npx playwright test
make reset                                   # curl -X POST localhost:8000/api/demo/reset
cd frontend && npm run dev                   # Vite dev server; proxies /api -> http://localhost:8000
```

Environment: Python 3.12 venv at `backend/.venv`, Node 22. The `.venv` that exists today is at `../.venv` (outside this repo, Python 3.11, nothing installed), so it doesn't match. Config lives in `backend/.env` (copy `.env.example`).

## Architecture

FastAPI serves both the JSON API (all under `/api`) and the built React app (falling back to `index.html` for `/staff/*`, `/owner`, `/drill/*`, `/backstage`). One uvicorn worker only, because background tasks must run exactly once. State is one SQLite file in WAL mode (`schema.sql`, 10 tables, live-mode columns created from the start). No auth except the optional owner PIN.

**Alert pipeline** (`ingest/` → `alerts/`): an `AlertSource` (`ingest/replay.py` reads `replay/alerts.json` by type and click; `ingest/wazuh.py` polls the Wazuh indexer every 5 s) yields `RawAlert`s → `normalise` → `filter` (level < 7 or no lesson → status `filtered`, counted as `hidden_count`) → `group` (same rule + agent within 10 min → `count++`) → store. `alerts/pipeline.py` is the only writer of `alerts`. Cards are produced per role by `lessons/engine.py`, which fills placeholders (`{agent_name}`, `{count}`, `{window_minutes}`, `{files_renamed}`) in `lessons/lessons.json`. An alert whose lesson has no text for a role is omitted for that role (the ransomware card is owner-only).

**Drills** (`drills/`): the server owns all state (lobby → open → review → open … → finished); phones only render `GET /drills/{code}` and post answers. `drills/engine.py` is the only writer of drill tables. Options never include `correct`/`feedback` until that player has answered. Only the host (owner) advances. Scenario JSON must have exactly one `correct` option per role per step. A drill option may name `BLOCK_IP`, but answering it must never create a real action.

**Actions / live mode** (`actions/`, flag `ACTIONS`): `propose.py` turns a lesson's `proposed_action` into an `actions` row after `targets.py` checks (valid IPv4, not on the explicit never-block list). `timeout.py` runs every 10 s: expired proposals either execute under the owner's standing rule or escalate to the backup approver; executed blocks past `expires_at` become `expired`. `wazuh_client.py` has `WazuhClient`, `FakeWazuhClient` and the real client. **Simulation is per alert, from `alerts.source`**: a replayed alert is always simulated, even with `ALERT_SOURCE=wazuh`, so the stage fallback can never reach Wazuh. Live scope is a single action: `BLOCK_IP` on rule 60204, delivered via the Wazuh API active-response command `netsh3600` bound to the dummy rule 100999.

**Restore check** (`restore/checker.py`): copies the backup into `restore_sandbox/` (the only folder it may write to), compares sha256 against `manifest.json`, and checks age and "always connected" exposure. `demo_backup/make.py` regenerates the synthetic 50-file backup (2 altered, 9 days old) on every reset; `--good` builds a passing backup for tests.

**Frontend** (React + Vite + react-router, no login): `api.js` has one function per contract route and throws `ApiError {status, error, message}`. `usePoll` keeps the last good data on failure (`stale: true`), pauses on hidden tabs and never overlaps requests. `session.js` keeps identity and drill membership in `localStorage` (every access wrapped in try/catch because Safari private mode throws).

## Conventions that cut across files

- **Contract is frozen.** `backend/contract.py` holds the Pydantic response models. Changing it needs all four owners and the contract tests change in the same merge.
- **Routes never touch SQL**; they call the owning module (`pipeline.py` writes alerts, `drills/engine.py` drill tables, `actions/*` actions).
- **Nothing calls `datetime.now()`**; everything takes the `Clock` from `clock.py` so tests use `FakeClock` to run the 5-minute and 1-hour waits instantly.
- **Four seams with fakes** (in `tests/conftest.py`): `AlertSource`, `WazuhClient`/`FakeWazuhClient` (records calls, sends nothing), `RewordProvider`/`NoneProvider`, `Clock`/`FakeClock`. `main.py` picks real vs fake from config once at start-up.
- **Wire format:** IDs are SQLite ints except drill codes (4-digit strings) and Wazuh rule IDs (strings). Times are ISO 8601 UTC with `Z`. Lists are wrapped in an object (`{"alerts": [...]}`), every field is always present (`null`, never missing), booleans are real booleans. Errors are always `{"error": "<code>", "message": "..."}`; the default FastAPI 422 is overridden to `invalid_request`/400.
- **Feature flags default off** (`AI_REWORD`, `ACTIONS`, `ALERT_SOURCE=replay`). A flagged-off route returns `not_enabled` (404).
- **Untrusted log text:** `log_fields` (e.g. `username_tried`, `source_ip`) are copied verbatim from alerts and the replay data deliberately contains a prompt-injection string. The frontend renders them as plain text nodes only, never `dangerouslySetInnerHTML`. The AI reword guard may receive only the already-filled `headline` and `why`, never log text, and falls back unless output is ≤ 200 chars with no changed numbers, new digits or links.
- **Wazuh credentials never leave the server**; TLS verification uses `WAZUH_CA_CERT` and is never turned off. `lab/` is never imported by the app.
- Kannada/Hindi translations apply to the alert card only, with per-string English fallback. Action IDs in translated steps never change.
