# ShieldMate frontend: test version (clinical UI)

A side-by-side copy of `../frontend/` with a more serious, clinical look, made to compare
before switching. The backend, the API contract and all alert/drill text are unchanged.

```
npm run dev                                   # http://localhost:5174 (the original stays on 5173)
SM_BASE=http://localhost:5174 npx playwright test   # e2e against this version (backend on :8000, ACTIONS=1)
npm test                                      # vitest
```

The backend serves only `frontend/dist`, so use the Vite server above to try this version.
To switch over for good: rename `frontend/` (e.g. to `frontend-old/`), rename this folder to
`frontend/`, and set its dev port in `vite.config.js` back to 5173.

What differs from `../frontend/`:

- **One theme.** The violet "bold" theme, Space Grotesk and the `?theme=` switch are gone.
  Navy accent, slate neutrals, 1px borders, 8-10px radii, no shadows. Red, amber and green
  appear only where they carry meaning.
- **Alert cards** have a severity strip ("Needs you now" + time) above the headline.
- **Drills read as a training exercise.** "Step 1 of 4" instead of a gold "MOMENT" badge,
  "Correct" / "Not the recommended action" instead of "Nice call! +1 for the team", a debrief
  with figures instead of the gold score ring, flat scene drawings.
- **Depth on the owner, IT and projector screens.** A closed "How ShieldMate decided" panel on
  every owner incident (Wazuh rule, level, grouped events, source, playbook, block check), a
  "Today's events" signal-vs-noise card, system health in the owner sidebar, an "Incident log",
  and a detection pipeline on the projector (renamed "Operations view").
- **First screen** keeps demo scaffolding (projector, Backstage, all screens) in a closed
  "Presenter tools" section and shows a monitoring status line.

The original README follows.

---

## ShieldMate frontend (original notes)

React + Vite port of the ShieldMate redesign (the original HTML/CSS/JS version is kept in
`docs/reference/vanilla-ui/`). It always talks to the FastAPI backend: there is no mock mode.

```
make start            # build, then FastAPI serves the app and /api on :8000 (the demo setup)
make dev              # uvicorn :8000 + Vite :5173 with hot reload (Vite proxies /api)
npm test              # vitest unit tests (src/**/*.test.js)
npm run e2e           # Playwright demo stories; needs `ACTIONS=1 make start` running. Presses Reset.
```

## Screens

| Address | Who | What |
| --- | --- | --- |
| `/` | anyone | Pick who uses this device |
| `/staff/:id` | Meena, Ravi | Today, the alert card (steps, Call IT, Done, "That was me"), `/history` |
| `/staff/:id/drill` | Meena, Ravi | Join by code, lobby, steps, debrief |
| `/owner` | Dr. Rao | Right now: block approval, ransomware incident, IT support, standing rule |
| `/owner/readiness` | Dr. Rao | Backup restore check, last drill, single points of failure |
| `/owner/drill` | Dr. Rao | Host a drill (start, advance, end now, restore check) |
| `/owner/notify` | Dr. Rao | Lock-screen preview of the approval request |
| `/it` | IT contact | Incidents: call received, notes, resolved |
| `/mission` | projector | Floor plan, stopwatch / CERT-In clock, people, live feed |
| `/backstage` | presenter | Replay, skip 5 min, simulation, reset |

Flags: with `ACTIONS` off, block approvals and the device strip from `/devices` are hidden; the
rest works. Turn the alert chime off with `VITE_SOUND=off` at build time.

## Layout

- `src/lib/` — `api.js` (one function per contract route), `usePoll.js`, `time.js` (server
  clock, formatting), `derive.js` (shared facts), `content.js` (wording only), `session.js`,
  `telemetry.js`, `fx.js` (buzz and chime).
- `src/components/` — shells (owner sidebar/tabs, staff tabs), shared UI, drill pieces, icons,
  the drill scene pictures.
- `src/pages/` — one file per screen.
- `src/styles/shieldmate.css` — the redesign's stylesheet, unchanged apart from font paths.

Log text from alerts (e.g. the username the attacker tried) is untrusted and is only ever
rendered as plain text.
