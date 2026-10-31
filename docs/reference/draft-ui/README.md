# ShieldMate web UI

The ShieldMate screens as a plain HTML, CSS and JavaScript web app. There is no app to install and no build step: open it in any browser, on a phone or a laptop.

It runs in two modes:

- **Demo data (mock).** The default. Everything works in the browser with made-up data, and no backend is needed. Use it to click through, rehearse and design.
- **Live server (http).** Every screen calls the FastAPI backend at `/api/...`, using the routes in the Software Design. Use it for the real demo, so that phones and the laptop share one set of data.

You switch between them in one file, `assets/js/config.js`.

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

Two more things to try:

- **"That was me":** on Meena's alert card, then replay the password attack again. The alert reopens.
- **The standing rule:** replay the password attack, then press *Skip 5 min* in Backstage. The block happens with no tap.

---

## 2. Hosting options

| Option | Use it for | Data shared between devices? | Needs internet? |
| --- | --- | --- | --- |
| A. Laptop only (`http.server`) | Designing, rehearsing on one laptop | Only between tabs of one browser | No |
| B. Laptop + phones on the hotspot, mock mode | Showing the screens on real phones | **No.** Each phone has its own demo data | No |
| C. FastAPI serves the pages, http mode | **The real demo** | **Yes**, through the backend | No |
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

### C. Served by the FastAPI backend (recommended for the demo)

The backend serves these pages and the API from one address, so nothing else is needed.

1. Copy this folder into the backend repo, for example as `frontend/`.
2. In `main.py`, mount it **after** all `/api` routes:
   ```python
   from fastapi.staticfiles import StaticFiles

   # ... all @app.get("/api/...") routes above this line ...
   app.mount("/", StaticFiles(directory="frontend", html=True), name="web")
   ```
3. In `frontend/assets/js/config.js`, set:
   ```js
   mode: "http",
   apiBase: "",   // same server
   ```
4. Run on all interfaces so phones can reach it:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
5. Phones open `http://<laptop-address>:8000` as in option B.

To test one browser tab against the backend without editing config, add `?api=http` to any address; `?api=mock` switches it back. The choice lasts for that tab.

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

Owner pages switch from the side menu to bottom tabs below 900 px wide.

---

## 4. Files

```
index.html, staff.html, drill.html            staff and start screens
owner.html, owner-readiness.html,
owner-drill.html, owner-notify.html           owner screens
backstage.html                                demo controls
assets/css/shieldmate.css                     all styles (colours and sizes at the top)
assets/fonts/                                 self-hosted fonts + licences (works offline)
assets/js/config.js                           mock or http mode  ← the only switch
assets/js/api.js                              every API call, one function per route
assets/js/mock-server.js                      the in-browser fake backend (mock mode)
assets/js/data.js                             clinic seed, lessons, translations, drill scenario
assets/js/ui.js                               shared helpers: escaping, time, polling, navigation
assets/js/pages/*.js                          one script per page
tests/e2e_demo_story.py                       automated run of the whole demo story
```

---

## 5. What the backend must provide (http mode)

`api.js` lists every call. Most routes are in the Software Design's API contract. These are **new**, needed by the screens:

| Route | Used by | Purpose |
| --- | --- | --- |
| `GET /api/activity` | Owner "What happened" | Events, newest first: `[{at, text, kind}]` |
| `GET /api/drills/current` | Staff Today, Drills | The running drill, or `null`: `{code, title, status}` |
| `POST /api/drills/{code}/end` | Owner drill | End a drill early |
| `PUT /api/alerts/{id}/steps/{n}` body `{staff_id, done, list}` | Alert card, owner checklist | `list: "owner"` ticks the owner checklist instead of staff steps |
| `GET /api/demo/status`, `POST /api/demo/skip` | Backstage | Mock only; Backstage works without them |

**Response shapes:** `mock-server.js` is the reference. Match what these functions return and the pages work unchanged:

- `alertView()`: alert cards, with `staff_view.{en,kn,hi}`, `owner_view.checklist`, `log_fields`, `certin_due_at`
- `actionView()`: block requests, with `status`, `decide_by`, `seconds_left`, `expires_at`, `decided_via`
- `drillView()`: what each player sees: `step`, `my_options`, `my_answer`, `team`, `results`, `restore_trigger`
- `devicesView()`: computers, with `status`, `status_label`, `tone`

Times are milliseconds since 1970 (JavaScript `Date.now()`). In Python: `int(time.time() * 1000)`.

Errors: any 4xx with `{"error": "...", "message": "..."}`. The page shows `message` as a short notice.

---

## 6. Safety built into the pages

- Everything from the data is escaped before it is shown (`SM_UI.esc`). Log text, such as the poisoned username, appears exactly as recorded and can't run as code.
- The block request always says it was proposed by fixed rules, not AI. In demo mode it is labelled "Simulated action", and the backup "Simulated backup".
- Every drill screen carries the PRACTICE banner.
- No external requests: fonts and scripts are all local.

---

## 7. Testing

The automated test runs the whole demo story in a real browser at phone and laptop sizes and checks 19 things: the alert card, the approval, grouping, "That was me", the standing rule, the drill, the restore check and the results.

```bash
pip install playwright
playwright install chromium
python tests/e2e_demo_story.py      # exits 1 on any failure; screenshots in tests/screenshots/
```

Also test by hand on one Android phone (Chrome) and one iPhone (Safari) at every gate (Testing Plan T2.11).

---

## 8. Known limits in this build

- **Kannada and Hindi are drafts.** Only the password alert card is translated. A fluent speaker must check them (Testing Plan T2.05).
- **Only the ransomware drill is playable.** Password guessing appears as "not playable yet".
- **CERT-In report drafting, approval by fingerprint or PIN, and real push notifications come after the demo.** The notification page is a preview.
- **The IT contact** (`Suresh (CareIT)`, `+910000000000`) is a placeholder in `data.js`. Change it before the demo.

Fonts: Atkinson Hyperlegible, Noto Sans Kannada, Noto Sans Devanagari and IBM Plex Mono, all under the SIL Open Font License (see `assets/fonts/`).
