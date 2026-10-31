# ShieldMate frontend

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
| `/staff/:id/drill` | Meena, Ravi | Join by code, lobby, game-style moments, results |
| `/owner` | Dr. Rao | Right now: block approval, ransomware incident, IT support, standing rule |
| `/owner/readiness` | Dr. Rao | Backup restore check, last drill, single points of failure |
| `/owner/drill` | Dr. Rao | Host a drill (start, advance, end now, restore check) |
| `/owner/notify` | Dr. Rao | Lock-screen preview of the approval request |
| `/it` | IT contact | Incidents: call received, notes, resolved |
| `/mission` | projector | Floor plan, stopwatch / CERT-In clock, people, live feed |
| `/backstage` | presenter | Replay, skip 5 min, simulation, reset |

Flags: with `ACTIONS` off, block approvals and the device strip from `/devices` are hidden; the
rest works. Turn the alert chime off with `VITE_SOUND=off` at build time. Theme: `?theme=calm`
or `?theme=bold` on any address (bold is the default).

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
