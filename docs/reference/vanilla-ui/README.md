# ShieldMate web UI

The ShieldMate screens as a plain HTML, CSS and JavaScript web app. There is no app to install and no build step: open it in any browser, on a phone or a laptop.

It runs in two modes:

- **Demo data (mock).** The default. Everything works in the browser with made-up data, and no backend is needed. Use it to click through, rehearse and design.
- **Live server (http).** Every screen calls the FastAPI backend at `/api/...`, using the routes in the Software Design. Use it for the real demo, so that phones and the laptop share one set of data.

You switch between them in one file, `assets/js/config.js`.

### IT support loop

Staff tick "Call Suresh" on their alert card. On `it.html`, Suresh taps **Call received**, adds notes, and marks it **resolved**, saying what he did. Dr. Rao sees each stage on his incident card, then **confirms** (the incident closes and moves to "Closed today") or sends it back with **Not fixed yet**. IT can't close an incident on its own. Every alert view carries `it: {status, called_by, called_at, received_at, resolved_at, resolved_note, closed_at, sent_back_at, log}`, with status `none`, `called`, `received`, `resolved` or `closed`.

### New in v3: built to excite the judges

| What | Where | How to switch |
| --- | --- | --- |
| **Bold brand** (violet, Space Grotesk headings) | every page | Default. Add `?theme=calm` to any address for the old blue look; `?theme=bold` switches back. The choice lasts for that tab. To change the default, edit `DEFAULT_THEME` in `assets/js/theme.js`. |
| **Quick polish**: alerts slide in and shake, the phone buzzes and chimes, countdowns tick every second | staff and owner pages | Always on. Sound needs one tap on the page first (browsers require it). Turn sound off with `sound: false` in `config.js`. Animations switch off for anyone with "reduce motion" set. |
| **Game-style drill**: scene picture per moment, A/B/C answers, team score, results ring, last month vs today bars | `drill.html` | Always on |
| **Mission control**: projector screen with the clinic floor plan, the attack line, the "spotted → blocked" stopwatch, the CERT-In clock, the drill scoreboard, people and a live feed | `mission.html` | Open it on the projector laptop |
| **Judges' mini-drill**: 2 questions on judges' phones, live bars on the projector, answers hidden until you tap Reveal | `judge.html`, `judge-tally.html` | **Off by default.** With the backend: `SM_JUDGE_DRILL=1 python backend/main.py`. In demo mode: `judgeDrill: true` in `config.js` (one browser only). |

**"Last month" is sample data.** There is no real earlier drill, so the comparison uses a made-up baseline (`PREVIOUS_DRILL` in `data.js`) and every screen labels it "sample data". Say so if a judge asks, or replace it with a real first drill you run with your team before the demo.

---

## 1. Try it in 1 minute (laptop)

You need Python 3 (already on most laptops).

```bash
cd shieldmate-web
python3 -m http.server 8000
```

Open **http://localhost:8000** and pick who you are.

Don't open `index.html` by double-clicking. Browsers limit pages opened as files, so always serve the folder.

### Walk through the demo story in one browser

In demo mode, the data lives in your browser. Open each person in a **separate tab of the same browser** and they update each other every 2 seconds:

1. **Tab 1:** Backstage. Press *Reset demo* twice.
2. **Tab 2:** Meena (`staff.html?staff=meena`). Make the window narrow, or use your browser's phone view.
3. **Tab 3:** Dr. Rao (`owner.html`).
4. In Backstage, press **Replay next** on *Password guessing*.
   - Meena gets the alert card.
   - Dr. Rao gets the approval request.
5. Tick Meena's steps, then tap *I've done these*. On Dr. Rao's tab, tap **Approve block**.
6. In Backstage, replay *Ransomware*. Dr. Rao sees the incident, the checklist and the CERT-In deadline.
7. **Drill:**
   - On Dr. Rao's tab, open *Drills* and press *Start team drill*.
   - Open `drill.html?staff=meena` and `drill.html?staff=ravi` in two more tabs and type the code.
   - Dr. Rao presses *Begin*, and everyone answers.
   - At moment 3, Dr. Rao's right answer shows **Test the backup now**.
8. **Readiness** shows the backup result and each person's drill results.
9. **Projector:** open `mission.html` in another tab (full screen, F11) at any point. It follows everything above live.

Two more things to try:

- **"That was me":** on Meena's alert card, then replay the password attack again. The alert reopens.
- **The standing rule:** replay the password attack, then press *Skip 5 min* in Backstage. The block happens with no tap.

---

## 2. Hosting options

| Option | Use it for | Data shared between devices? | Needs internet? |
| --- | --- | --- | --- |
| A. Laptop only (`http.server`) | Designing, rehearsing on one laptop | Only between tabs of one browser | No |
| B. Laptop + phones on the hotspot, mock mode | Showing the screens on real phones | **No.** Each phone has its own demo data | No |
| C. The ShieldMate backend (`python backend/main.py`) | **The real demo** | **Yes**, through the backend | No |
| D. Static website (GitHub Pages, Netlify) | Sharing a clickable prototype with judges or mentors | No | Yes |

### A. Laptop only

See section 1.

### B. Phones on the laptop's hotspot (mock mode)

1. Turn on the laptop's mobile hotspot and connect the phones to it.
2. Serve the folder on all network interfaces:
   ```bash
   python3 -m http.server 8000 --bind 0.0.0.0
   ```
3. Find the laptop's address on the hotspot:
   - **Windows:** `ipconfig` (often `192.168.137.1`)
   - **macOS:** `ipconfig getifaddr en0` (or the hotspot interface)
   - **Linux:** `hostname -I`
4. On each phone, open `http://<laptop-address>:8000`.
5. If a phone can't connect, allow Python through the laptop's firewall for private networks. Some phone hotspots block devices from reaching each other, so use the **laptop's** hotspot, not a phone's.

In mock mode, each phone keeps its own data. Use B to show the screens on phones, and C when the phones must update together.

### C. The ShieldMate backend (recommended for the demo)

The backend is included in `backend/main.py`. One process serves the pages **and** the API, so every phone on the hotspot shares one set of data. It is a route-for-route port of the in-browser mock, so anything that works in demo mode works here.

1. Install once (needs Python 3.9 or newer):
   ```bash
   pip install fastapi uvicorn
   ```
2. From the `shieldmate-web` folder:
   ```bash
   python backend/main.py
   ```
   It listens on port 8000 on every network interface. Use `PORT=9000 python backend/main.py` for another port.
3. Phones open `http://<laptop-address>:8000`, as in option B.

You don't need to edit `config.js`. The backend serves it with `mode: "http"` switched on. The same folder still runs in demo mode from `python3 -m http.server`.

| Setting | How | What it does |
| --- | --- | --- |
| Judges' drill | `SM_JUDGE_DRILL=1 python backend/main.py` | Turns on `judge.html` and `judge-tally.html` for every device |
| Real Wazuh alerts | `SM_INGEST_TOKEN=<secret> python backend/main.py` | Turns on `POST /api/ingest/alert` (see section 5) |
| API reference | open `/api/docs` | Lists the routes |

**State** is saved to `backend/state.json` after every change, so a restart keeps the demo where it was. **Reset demo** in Backstage wipes it. The backend never serves its own files, the tests or `state.json` to browsers.

**Scenario and lesson text** come from `assets/js/data.js`, the same file the screens use. The backend reads an export of it, `backend/shieldmate_data.json`. After editing `data.js`, run `node tools/export-data.js`. If Node is installed, the backend also re-exports by itself on start.

### Live mode: real Wazuh alerts and real blocks

Off by default. The backend runs on Backstage replays until you turn this on. It follows the Wazuh Integration Guide: lab setup, users, the block script and the verification order are all there.

1. `pip install httpx`
2. Copy `backend/.env.example` to `backend/.env` and fill in the Wazuh addresses and the two passwords. Set `ALERT_SOURCE=wazuh`. Never commit `.env`.
3. `python backend/main.py`. It prints where alerts come from and whether blocks are sent or simulated. Backstage shows **Wazuh: connected** or the last error.

| What happens | Detail |
| --- | --- |
| Alerts in | Every `WAZUH_POLL_SECONDS`, it reads rule 60204 (becomes the card) and 60122 (each failed logon) for ShieldMate's devices only. It starts from "now", so old lab alerts don't flood the demo. The card's count is the real number of failed logons from that address |
| Block out | Only after Dr. Rao approves or the standing rule acts. Plan B (`!shieldmate-block.exe`, add and delete) or Plan A (`!netsh.exe`, add only). The IP is checked again before sending, and never-block addresses are refused |
| Did it work? | For 30 s after sending, any new failed logon from that address (after a 5 s grace) means it didn't. Then the owner sees **The block didn't take effect** with **Try the block again**, mission control says so, and the owner is told to call IT |
| Ends | Plan B: Undo and expiry send `delete`; blocks that expired while ShieldMate was off are lifted on start |
| Wazuh down | Backstage and the owner badge say **Wazuh not reachable**; Replay still works |

The ransomware card stays on replay. The lab only covers the password attack.

Screens always say where alerts come from:

| Mode | Owner badge | Mission control |
| --- | --- | --- |
| Demo data | Demo data · replay mode | recorded alerts |
| Backend with replays | Recorded alerts · replay mode | recorded alerts |
| Live | Live · Wazuh connected | live from Wazuh |

Test it without the lab: `python tests/live_wazuh_test.py` runs the backend against a stand-in Wazuh (`tests/fake_wazuh.py`) and checks 19 things, including that no password or token ever appears in the API, the saved state or the log. It takes about 90 s.

### D. Static website (shareable prototype)

Upload the whole folder as a static site, for example GitHub Pages (Settings → Pages → deploy from branch) or Netlify Drop (drag the folder in). It runs in mock mode, so every visitor gets their own demo data. Don't use this for the live demo: it needs internet and has no backend.

---

## 3. Screens

| Screen | Address | Phone | Laptop |
| --- | --- | --- | --- |
| Who's using this device? | `index.html` | ✓ | ✓ (centred) |
| Staff · Today, all clear | `staff.html?staff=meena` | ✓ | ✓ (centred) |
| Staff · Alert card (tickable steps, Call IT, languages, log details, "That was me") | same, once an alert is open | ✓ | ✓ |
| Staff · History | `staff.html?staff=meena&view=history` | ✓ | ✓ |
| Staff · Join drill, lobby, each moment, results | `drill.html?staff=ravi` | ✓ | ✓ |
| Owner · Right now (approval card, ransomware incident, computers, what happened) | `owner.html` | ✓ bottom tabs | ✓ side menu |
| Owner · Readiness (backup check, team results, single point of failure) | `owner-readiness.html` | ✓ | ✓ |
| Owner · Start and host a drill (restore check at moment 3) | `owner-drill.html` | ✓ | ✓ |
| Owner · Phone approval notification (preview) | `owner-notify.html` | ✓ | ✓ |
| Backstage (demo controls) | `backstage.html` | ✓ | ✓ |
| IT support panel (Suresh, CareIT): incoming calls, technical details, notes, Mark resolved | `it.html` | ✓ | ✓ |
| Mission control (projector) | `mission.html` | – | ✓ (designed for 1280 px and wider) |
| Judges' mini-drill (switch) | `judge.html` | ✓ | ✓ |
| Judges' results (switch, projector) | `judge-tally.html` | – | ✓ |

Owner pages switch from the side menu to bottom tabs below 900 px wide.

---

## 4. Files

```
index.html, staff.html, drill.html            staff and start screens
it.html                                       IT support panel (the clinic's IT contact)
owner.html, owner-readiness.html,
owner-drill.html, owner-notify.html           owner screens
backstage.html                                demo controls
mission.html                                  projector screen
judge.html, judge-tally.html                  judges' mini-drill (off unless judgeDrill: true)
assets/css/shieldmate.css                     all styles (colours and sizes at the top)
assets/fonts/                                 self-hosted fonts + licences (works offline)
assets/js/config.js                           mock or http mode, judgeDrill, sound
assets/js/theme.js                            bold or calm look (?theme=)
assets/js/scenes.js                           drill scene pictures (plain SVG)
assets/js/api.js                              every API call, one function per route
assets/js/mock-server.js                      the in-browser fake backend (mock mode)
assets/js/data.js                             clinic seed, lessons, translations, drill scenario
assets/js/ui.js                               shared helpers: escaping, time, polling, navigation
assets/js/pages/*.js                          one script per page
backend/main.py                               the FastAPI backend (pages + API, one process)
backend/wazuh.py                              live mode: reads Wazuh alerts, sends and confirms blocks
backend/.env.example                          live-mode settings (copy to .env; never commit .env)
backend/shieldmate_data.json                  export of data.js for the backend
tools/export-data.js                          re-export after editing data.js
tests/e2e_demo_story.py                       automated run of the whole demo story
tests/live_wazuh_test.py, fake_wazuh.py       live mode against a stand-in Wazuh
```

---

## 5. The backend's routes

`backend/main.py` implements every route in `api.js`, with the same shapes as `mock-server.js`. Change both together: if you change a shape in one, change it in the other, then run the tests in both modes (section 7).

Routes beyond the Software Design's original contract:

| Route | Used by | Purpose |
| --- | --- | --- |
| `GET /api/activity` | Owner "What happened", mission control | Events, newest first: `[{at, text, kind}]` |
| `GET /api/drills/current` | Staff Today, Drills, mission control | The running drill, or `null`: `{code, title, status}` |
| `POST /api/drills/{code}/end` | Owner drill | End a drill early |
| `PUT /api/alerts/{id}/steps/{n}` body `{staff_id, done, list}` | Alert card, owner checklist | `list: "owner"` ticks the owner checklist instead of staff steps |
| `GET /api/demo/status`, `POST /api/demo/skip`, `/demo/replay/{type}`, `/demo/reset` | Backstage | Demo controls |
| `POST /api/judge/answers`, `GET /api/judge/tally` | Judges' drill | Only used when the judges' drill is on |
| `GET /api/alerts?include=closed` | Owner "Closed today", IT panel | Also returns incidents the owner has closed (`closed: true`) |
| `POST /api/alerts/{id}/it` body `{action, note}` | IT panel | `action`: `received`, `note` or `resolved`. Resolving needs a note of at least 5 characters saying what was done |
| `POST /api/alerts/{id}/close` body `{staff_id, confirm, note?}` | Owner | Owner only, and only once IT has marked it resolved. `confirm: true` closes the incident; `false` sends it back to IT |
| `POST /api/ingest/alert` | Your Wazuh poller | Off unless `SM_INGEST_TOKEN` is set. Body: `{token, rule_id, agent_name, count?, window_minutes?, source_ip?, username?, files?}`. Rules without a lesson (only 60204 and 100201 have one) are refused |

The drill view also returns `team_score`, `previous` (the sample baseline) and `step.devices`. Times are milliseconds since 1970 (JavaScript `Date.now()`). Errors are any 4xx with `{"error": "...", "message": "..."}`. The page shows `message` as a short notice.

**Blocks are simulated unless live mode is on** (section 2, "Live mode"). The real calls are in `backend/wazuh.py`; `execute_block()` and `release_block()` in `main.py` are the only places that start or end a block.

---

## 6. Safety built into the pages

- Everything from the data is escaped before it is shown (`SM_UI.esc`). Log text, such as the poisoned username, appears exactly as recorded and can't run as code.
- The block request always says it was proposed by fixed rules, not AI. In demo mode it is labelled "Simulated action", and the backup "Simulated backup".
- Every drill screen carries the PRACTICE banner.
- No external requests: fonts and scripts are all local.

---

## 7. Testing

The automated test runs the whole demo story in a real browser at phone and laptop sizes and checks 50 things: the alert card, the approval, grouping, "That was me", the standing rule, the drill (game style), the restore check, the results and last month vs today, mission control in every state, both themes, the judges' drill with its switch on and off, and the IT support loop (call, pick up, resolve, send back, confirm).

```bash
pip install playwright
playwright install chromium
python tests/e2e_demo_story.py      # demo mode; exits 1 on any failure; screenshots in tests/screenshots/

# The same checks against the backend (start it first in another terminal):
SM_BASE=http://127.0.0.1:8000/ python tests/e2e_demo_story.py
```

Against the backend there is one extra check: a second browser with no shared storage, standing in for a second phone, sees the same data.

Also test by hand on one Android phone (Chrome) and one iPhone (Safari) at every gate (Testing Plan T2.11).

---

## 8. Known limits in this build

- **Kannada and Hindi are drafts.** Only the password alert card is translated. A fluent speaker must check them (Testing Plan T2.05).
- **Only the ransomware drill is playable.** Password guessing appears as "not playable yet".
- **CERT-In report drafting, approval by fingerprint or PIN, and real push notifications come after the demo.** The notification page is a preview.
- **Mission control and the judges' drill only sync across devices with the backend (option C).** In mock mode, open them as tabs in the same browser as the other screens.
- **Skip 5 min with the backend:** the server's clock moves ahead, but the countdowns on screens still use each device's own clock. The block happens correctly; a countdown that was already showing may be off by 5 minutes until it disappears.
- **Live mode is tested against a stand-in Wazuh, not your lab.** The calls match the Integration Guide, but run its verification table (12 checks) on the real VMs before the demo.
- **The backend saves state to a JSON file, not SQLite** as the Software Design planned. For one clinic on one laptop that's simpler and just as safe; switch only if you need many clinics.
- **No QR code** for the judges' drill (no offline QR library). The results screen shows the address in large text; print a QR code for it before the demo if you want one.
- **The IT contact** (`Suresh (CareIT)`, `+910000000000`) is a placeholder in `data.js`. Change it before the demo.

Fonts: Atkinson Hyperlegible, Noto Sans Kannada, Noto Sans Devanagari, IBM Plex Mono and Space Grotesk, all under the SIL Open Font License (see `assets/fonts/`).
