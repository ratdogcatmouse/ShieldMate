# Frontend changes: simulation controls, backstage token, impact priority

These changes connect the frontend to backend features that were already merged but had no UI:
the attack simulation (`/demo/simulate`, flag `SIMULATE`) and the impact priority on alerts
(`impact` field and `?sort=impact`). They also fix a gap in how Backstage calls authenticate.

## 1. Attack simulation controls (Backstage)

**Where:** `src/routes/Backstage.jsx`, `src/api.js`

- New API functions in `api.js`, one per contract route:
  - `simulateStart(scriptId)` → `POST /demo/simulate/{script_id}`
  - `simulateStop()` → `POST /demo/simulate/stop`
  - `getSimulate()` → `GET /demo/simulate`
  - Mock mode serves `backend/fixtures/demo_simulate_*.json`, like every other route.
- Backstage has a new **Attack simulation** section:
  - A **Start** button for each script (`phish_owner`, `ransom_wave`, `credential_sprawl`).
    The list is hard-coded in `SIMS` in `Backstage.jsx`, because the backend has no route that lists scripts. Add a new script there when you add one to `backend/replay/sim/`.
  - A **Stop attack** button, enabled only while a run is going.
  - A status line (for example `Running · phish_owner`, or `Stopped · phish_owner · stopped by Backstage`) polled every 2 s.
  - Start buttons are disabled while a run is in progress.
- The section only appears when `GET /status` reports `flags.SIMULATE: true`. With the flag off, the page looks as before.

## 2. Backstage token

**Where:** `src/session.js`, `src/api.js`, `src/routes/Backstage.jsx`, `src/styles/tokens.css`

Before this change the frontend never sent `X-Backstage-Token`, so Replay and Reset would fail with a 401 as soon as `BACKSTAGE_TOKEN` was set on the server.

- `session.js`: `getBackstageToken` / `setBackstageToken`, stored in `sessionStorage` (cleared when the tab closes), wrapped in the same try/catch as the other storage helpers.
- `api.js`: calls made with `who: "backstage"` now send `X-Backstage-Token` when a token is saved.
- `Backstage.jsx`: when the server answers `pin_required` or `pin_invalid`, a token field and **Save token** button appear. After saving, retry the action.
- With no token set on the server, nothing changes and the field never shows.

## 3. Impact priority

**Where:** `src/components/Badge.jsx`, `src/components/AlertCard.jsx`, `src/routes/Owner.jsx`, `src/api.js`

- `Badge.jsx`: new `ImpactPill`, showing "Low / Medium / High / Critical impact" (grey, amber, red, red). It renders nothing when `impact` is `null` (filtered noise or unknown devices).
- `AlertCard.jsx` (staff phone): shows the pill on open alerts.
- `Owner.jsx`: shows the pill next to "Needs you now", plus the backend's `impact.reason` line under the card.
- `api.js`: `getAlerts(role, lang, sort)` takes an optional `sort` (`"time"` default, or `"impact"`). The owner page requests `"impact"`, so the highest-impact alert is first. Staff phones keep newest first.

## How it was checked

- `vite build` passes in both `VITE_API_MODE=http` and mock mode.
- Real Chrome against a live server (`SIMULATE=1`, `BACKSTAGE_TOKEN=tok`):
  - the simulation section appears;
  - the token field appears after the 401, and Replay works once the token is saved;
  - starting a script shows "Running", and Stop changes it to "Stopped";
  - the owner page shows a "High impact" badge with its reason;
  - no page errors (the only console errors were the expected 401s before the token was entered).

## Not covered

- Simulation runs are not recorded in the event log (no `sim.*` types in `backend/eventlog/catalogue.py`).
- There are no automated frontend tests for these changes; `frontend/e2e/` is empty.
- Kannada and Hindi: the new strings (pill labels, Backstage text) are English only. Backstage is operator-facing, but the impact pill appears on staff phones.
