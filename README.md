# ShieldMate

**A security team for a small business that can't afford one.**

India's small clinics, shops and offices run on a few shared PCs. They have no IT department and no one watching the network. To an attacker, that makes them the easiest targets there are. When ransomware hit AIIMS Delhi in 2022, one of the best-funded hospitals in the country lost its systems for days. A family clinic has far fewer defences and no one to call. Attackers have already industrialised: phishing, fake tech-support calls and supplier bank fraud are cheap, automated and aimed at exactly these businesses. One bad click can wipe out patient records, billing and the business itself. Under CERT-In rules, the owner then has **six hours** to report the incident.

ShieldMate gives that clinic a security operations centre that runs on everyone's phone. It detects attacks live and tells every person, in plain words, exactly what to do.

## Live threat detection

ShieldMate connects to a [Wazuh](https://wazuh.com) server on the clinic's network and checks it for new alerts every 5 seconds. Password guessing, suspicious logins, phishing activity and ransomware renaming files all reach the right phones within seconds of happening. Repeated hits from the same attack are grouped into one alert, and low-level noise is filtered out, so the team only hears about what matters. The `/mission` screen shows a live feed of every attack as it arrives.

## Clear decisions for non-technical teams

Security tools are built for analysts. A receptionist faced with "rule 60204, level 10" freezes, and an owner can't tell a nuisance from a disaster. Every alert in ShieldMate becomes a card that answers four questions, written for the person reading it:

1. **What's happening?** "Someone is repeatedly guessing the password on the reception PC."
2. **What do we know?** "8+ wrong passwords in 4 minutes. Not a confirmed break-in yet."
3. **Why does it matter?** "One correct guess opens patient records."
4. **What do I do right now?** Short steps to tick off, such as "Don't log in from this PC" and "Call your IT contact."

Each role gets different wording and different steps. Staff are told what to stop doing. The owner is told what to decide. The IT contact gets the technical detail. Alerts are ranked by **what's actually at risk**: an attack on the file server holding patient records and billing outranks the same attack on the front-desk PC. When a decision is needed, it reaches one named person as a single yes-or-no question, with a backup approver if they don't answer. Nobody has to interpret a log or guess whose job it is.

## What else it does

- **Blocks the attacker with one tap.** The owner approves blocking the attacker's address from their phone. If no one answers, a standing rule acts, or the request goes to a backup approver. Safety checks stop it from ever blocking the clinic's own router or servers.
- **Runs practice drills.** Like a fire drill, but for a cyber attack. The whole team joins from their phones with a 4-digit code. They practise ransomware, a phishing email to the doctor, a fake "tech support" call, a supplier bank-detail swap and password guessing. Each person gets choices written for their own role, then the team reviews the results together.
- **Checks that the backups will actually restore.** It test-restores the backup in a sandbox and checks file hashes, the backup's age and whether the backup stays permanently connected to the network. Ransomware would encrypt a backup like that too. A failed check opens an IT incident, and it stays open until a retest passes.
- **Watches the reporting deadline.** The owner's screen shows the CERT-In countdown and builds the incident timeline as events happen.
- **Explains anything on screen.** A built-in "?" assistant, powered by an n8n AI agent, answers "what does this mean?" for any alert or drill step.

## Run it

Requires Python 3.12 and Node 24.

```bash
make install        # backend venv + frontend packages
./start.sh          #for a mac - builds the frontend, serves app + API on http://localhost:8000
```

Then open one screen per phone or browser tab:

| Screen | URL |
|---|---|
| Clinic owner | `/owner` |
| Staff (Meena, Ravi) | `/staff/1`, `/staff/2` |
| IT contact | `/it` |
| Live attack feed | `/mission` |
| Demo controls (replay attacks, start drills, reset) | `/backstage` |

The demo replays recorded attacks, so you don't need a Wazuh server. To connect a real Wazuh lab, copy `backend/.env.example` to `backend/.env` and set `ALERT_SOURCE=wazuh` and `ACTIONS=1`.

Other commands: `make test` runs pytest and vitest. `make smoke` boots the full stack and checks it end to end. Run `make help` to see them all.

## How it's built

- **Backend:** FastAPI with SQLite. An alert passes through `ingest` (Wazuh or replay), then normalise, filter, group, and finally role-specific lesson cards.
- **Frontend:** React and Vite, with one screen per role. There is no login: each person's address is their identity.
- **Safety:** Alert text from logs is always treated as untrusted, and the replay data includes a prompt-injection test. Wazuh credentials never leave the server. Every risky feature stays off until a flag turns it on.

Design and API docs are in [`docs/`](docs/).

## Team

Ishaan  · Cetas · Abhiram · Kishaann 
