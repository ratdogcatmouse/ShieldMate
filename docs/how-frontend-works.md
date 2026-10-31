# How the ShieldMate frontend works

A walkthrough of `frontend/` (React + Vite + react-router) and the demo workflow it drives.
The backend contract is in `backend/contract.py`; ownership and decisions are in [DECISIONS.md](DECISIONS.md).

## The shape of the app

- **Stack:** React + Vite + react-router, with no login and no mock mode. It always talks to the FastAPI
  backend under `/api` (`npm run dev` proxies to `localhost:8000`; in production FastAPI serves the built app).
- **Identity is the address.** [Start.jsx](../frontend/src/pages/Start.jsx) asks "Who's using this device?" once.
  Then the URL carries the role:
  - `/staff/:id` for Meena and Ravi
  - `/owner` for Dr. Rao
  - `/it` for the IT contact
  - `/mission` for the projector
  - `/backstage` for demo controls
- **Everything is polled, not pushed.** [usePoll.js](../frontend/src/lib/usePoll.js) fetches every 2 s. It pauses
  on hidden tabs, never overlaps requests, and keeps the last good data (`stale: true`) when the network drops.
  After any tap, `refresh()` re-polls immediately. The server owns all state and the phones only render it.
- **Wiring:**
  - [api.js](../frontend/src/lib/api.js): one function per contract route; throws `ApiError {status, error, message}`.
  - [derive.js](../frontend/src/lib/derive.js): facts several screens share (device strip, CERT-In deadline, the
    activity timeline).
  - [content.js](../frontend/src/lib/content.js): presentation wording only. Alert and drill text always comes
    from the backend.
  - [session.js](../frontend/src/lib/session.js): language and drill player ids in storage, every access in
    try/catch (Safari private mode throws).

## Routes

| Path | Page | Who |
|---|---|---|
| `/` | Start (pick a person) | everyone |
| `/staff/:id`, `/staff/:id/history` | Staff: Today, the alert card, History | front desk, billing |
| `/staff/:id/drill` | StaffDrill: join, lobby, moments, results | staff |
| `/owner` | OwnerNow: "Right now" | owner |
| `/owner/readiness` | OwnerReadiness | owner |
| `/owner/drill` | OwnerDrill: host a drill | owner |
| `/owner/notify` | OwnerNotify: lock-screen preview of an approval request | owner |
| `/it` | ItPanel | IT contact |
| `/mission` | Mission control (read-only projector screen) | audience |
| `/backstage` | Backstage (demo controls) | presenter |

## The demo story, step by step

1. **Backstage** ([Backstage.jsx](../frontend/src/pages/Backstage.jsx)) drives the demo.
   - *Reset* clears alerts, drills and backup tests, and puts the clock back.
   - *Replay next* injects a recorded alert. Password guessing has two clicks (the count goes from 8+ to 12+);
     ransomware has one.
   - *Skip 5 min* shows the standing rule acting.
   - With `SIMULATE` on, it can also play scripted multi-phase attacks.
2. **An attack arrives.** The backend filters, groups and stores the alert and builds a card per role.
3. **Staff phone** ([Staff.jsx](../frontend/src/pages/Staff.jsx)):
   - A new card slides in, shakes and chimes once per tab.
   - It shows a headline, what we know, and numbered steps that can be ticked. Ticks are keyed by action ID, so a
     tick shows on every role's card.
   - The "Call IT" step opens `tel:`.
   - Raw log text sits in a collapsible block, rendered as plain text (an injection string is in the replay
     data on purpose).
   - The staff member taps **Tell Dr. Rao** (`markDone`) or **That was me** (`sayMine`), which pauses the alert
     for an hour. If the attack repeats, it reopens.
   - English, Kannada and Hindi are available per card, falling back to English per string.
4. **Owner "Right now"** ([OwnerNow.jsx](../frontend/src/pages/OwnerNow.jsx)):
   - Decisions come first. The **ApprovalCard** ("Block the attacker for 60 minutes?") has a countdown, plus
     Approve and Decline.
   - If the owner doesn't answer, the standing rule blocks the address, or the backup approver is asked.
   - After approval the card shows **Blocked**, with Undo and an expiry time.
   - If the block fails or the target is protected, it shows the **NotBlocked** card and tells the owner to call IT.
   - For ransomware it shows the incident header, a CERT-In 6-hour countdown, and a checklist. The checklist
     includes **Test backup now**, which runs `/restore/run`.
   - The **device strip** (Computers) goes ok -> under attack -> protected, or files locked -> isolated.
   - The standing-rule toggle and a "What happened" timeline sit alongside.
5. **IT loop:**
   - Staff tick "Call IT", and the ticket appears on `/it` ([ItPanel.jsx](../frontend/src/pages/ItPanel.jsx)) and rings.
   - IT taps **Call received**, adds notes, then **Mark resolved**. The resolved note must be at least 5 characters.
   - The owner's IT card (Called -> Picked up -> Resolved -> You confirmed) then offers **Confirm and close** or
     **Not fixed yet**, which sends it back.
6. **Mission control** ([Mission.jsx](../frontend/src/pages/Mission.jsx)) is read-only for the projector:
   - an SVG floor plan with the attacker line, then a "BLOCKED" marker
   - the attack-spotted-to-blocked stopwatch, or the CERT-In clock
   - a People panel and a live feed

## Drills and readiness

- **Owner hosts a drill** ([OwnerDrill.jsx](../frontend/src/pages/OwnerDrill.jsx)): pick a scenario and start
  (this creates a 4-digit code and the host's own player), then lobby, moments (open -> review -> next), results.
- **Staff join** at `/staff/:id/drill` ([StaffDrill.jsx](../frontend/src/pages/StaffDrill.jsx)): type the code, wait
  in the lobby, pick an option each moment (feedback appears after answering), see results.
- **Server rules:** only the host advances, and the server owns all drill state. A drill option may name
  `BLOCK_IP`, but answering it never creates a real action. The device strip and the owner's impact pills follow
  each step.
- **A drill moment can trigger the same restore check** as the ransomware checklist.
- **Readiness** ([OwnerReadiness.jsx](../frontend/src/pages/OwnerReadiness.jsx)) summarizes "if ransomware hit
  today": the backup check (fresh, intact, out of reach), the last drill's score, and single points of failure.

## Cross-cutting

- **Telemetry** ([telemetry.js](../frontend/src/lib/telemetry.js)) batches `ui.*` events to `POST /api/events`,
  tagged with a per-tab `X-Session-Id`. API errors are reported at most once per route every 30 s.
- **Server clock:** `App.jsx` polls `/status` so countdowns follow the server, and Backstage's "skip ahead" works.
- **Auth:** only the optional owner PIN (`X-Owner-Pin`) and Backstage token (`X-Backstage-Token`), sent as
  headers when set.
- **Safety:** log text (`log_fields`) is always rendered as a plain text node; there is no `dangerouslySetInnerHTML`
  anywhere.

## Where the attack-notification work lands

See [abhiram-notifications.md](abhiram-notifications.md) for the checklist.

- **Nothing in the frontend consumes `kind` or `quick_action` yet.** Only `OwnerNotify`, `OwnerNow` and `Mission`
  fetch notifications, and all of them ask for `owner`. `Staff.jsx` doesn't poll notifications at all.
- **Duplicate timeline lines:** `activity()` in `derive.js` adds every owner notification to the timeline (the
  "What happened" panel on `OwnerNow` and the live feed on `Mission`). Each new alert now produces an alert line
  plus an `attack` note with the same headline, so those panels will show it twice. The frontend should drop
  `kind === "attack"` notes from `activity()`.
- **Owner approval card:** `OwnerNow`'s ApprovalCard already covers the owner's Block button, and
  `OwnerNotify` builds its own approval card from `/actions`. An owner attack note would repeat both, so Abhiram
  needs to decide which one it defers to.
