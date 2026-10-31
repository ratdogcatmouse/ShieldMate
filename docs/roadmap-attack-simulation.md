# Roadmap: Attack Simulation + Impact Priority (post-demo backlog, increments 7–8)

Status: **proposal**, extends the "After the demo" backlog in the Development Plan.
Everything here ships behind flags, default off — the replay demo stays the stage fallback until T8.10 passes.
Read after [DECISIONS.md](DECISIONS.md); where this doc changes the contract, the
frozen-contract rule applies (all four owners + contract tests in the same merge).

## The two features, in one breath

1. **Attack simulation.** Instead of Backstage pressing two replay buttons, an *attacker
   script* runs: a multi-phase cyber attack that happens over real time. ShieldMate
   detects it through the existing alert pipeline, the cards and steps tell the team what's
   wrong, and the simulation **branches on what the team does** — contain it fast and the
   encrypt wave never happens. The end screen says *contained in 4:12*, not *script finished*.
2. **Impact priority.** Every alert and device carries an **impact level** (low / medium /
   high / critical) computed from *what's at risk*: the data on the compromised device and
   the importance of the compromised account. The boss's machine getting phished outranks
   the reception PC; a ransomware wave on FILE-SERVER (patient records + billing) is
   critical, a wrong password on DOCTOR-PC is medium. The owner queue and the drill's
   results are ordered and weighted by that number.

Why both together: impact scoring gives the team a *reason* to act fast, and the
simulation gives them something to act on. Each is independently demoable.

---

## What we already have (build on this, don't rebuild it)

| Existing piece | Reuse for simulation | Reuse for impact |
|---|---|---|
| `AlertSource` seam (`ingest/source.py`) + `next_batch()` poll loop | The simulator **is a new `AlertSource`** — everything downstream (normalise → filter → group → cards → actions) runs unchanged | — |
| `replay/alerts.json` injection (`ingest/replay.py`) | Sim scripts are the *dynamic* version of the same records; replay stays the no-lab fallback | — |
| `lessons.json` cards + `drill_scenario` link | "Practise this with the team" already starts a drill from a live alert — the simulation's end-state handoff is nearly free | card copy can quote the impact reason |
| `drills/scoring.py` (T1.11 miss-tracking) | Sim outcome ("contained/spread") feeds the results screen | Weight missed actions by impact |
| `db.reset()` + `RUNTIME_TABLES` | New runtime tables just join the reset list | — |
| `FakeClock` + `FakeWazuhClient` | Deterministic sim tests: run the whole attack in milliseconds | — |
| `lab/attack.sh` | **Tier 1** real attacker against the Wazuh VM; sim is **Tier 2** for when the lab is off | — |

Rules we keep (from the plans): routes never touch SQL; nothing calls `datetime.now()`;
the sim **never sends anything to Wazuh** (same safety rule as decision 12); `lab/` is
never imported; log text stays untrusted.

---

## Feature 1 — Attack simulation (increment 7, gate T8)

### 1.1 Two tiers of "proper simulation"

- **Tier 1 — real lab (Kishaann):** `lab/attack.sh` becomes a *phased* attacker:
  `--phase failures|success|lateral|encrypt`, each phase a timed loop, auto-stops when
  its source IP is blocked (the `TIMED OUT (blocked)` line in the script is already the
  stop condition). The Wazuh indexer carries genuinely real alerts; ShieldMate just
  reacts. This is the gold standard, and it only needs the script split into phases +
  a `--auto` mode that walks the phases.
- **Tier 2 — in-app simulator (Ishaan/Cetas):** `ingest/simulator.py`, an `AlertSource`
  that *generates* Wazuh-shaped alerts in-process from an attack script. No lab needed,
  works on the demo rig or any laptop. This section is about Tier 2; Tier 1 shares the
  same attack-script format, so a script runs identically on both tiers.

### 1.2 Attack script format (content file, reviewed like a lesson)

New file: `replay/sim/{id}.json` (content, committed; same review bar as `lessons.json`).

```json
{
  "id": "ransom_wave",
  "title": "Ransomware wave: reception PC → file server",
  "attacker": {"ip": "192.168.1.57", "account": "frontdesk"},
  "sim_time_ms_multiplier": 20,
  "phases": [
    {"at_ms": 0,   "label": "password storm",
     "alert": {"rule": {"id": "60204", "level": 10}, "agent": {"name": "RECEPTION-PC"},
               "data": {"win": {"eventdata": {"targetUserName": "frontdesk", "ipAddress": "192.168.1.57", "logonType": "3", "eventID": "4625"}}}},
     "shieldmate": {"failures": 8, "window_minutes": 4}},
    {"at_ms": 90000, "label": "first login succeeds",
     "alert": {"rule": {"id": "60106", "level": 3}, "agent": {"name": "RECEPTION-PC"},
               "data": {"win": {"eventdata": {"targetUserName": "frontdesk", "logonType": "2"}}}},
     "cancel_if": "CONTAINED"},
    {"at_ms": 180000, "label": "encryption on the file server",
     "alert": {"rule": {"id": "100201", "level": 12}, "agent": {"name": "FILE-SERVER"},
               "data": {"win": {"eventdata": {"targetUserName": "frontdesk"}}}},
     "shieldmate": {"files_renamed": 37, "window_minutes": 1},
     "cancel_if": "CONTAINED"}
  ]
}
```

- `at_ms` is *sim time* (multiplied by `sim_time_ms_multiplier` into real time, so the
  demo runs in watchable minutes; tests set the multiplier to 1 and drive `FakeClock`).
- **`cancel_if: "CONTAINED"`** is the branch: when the team's correct response lands
  (a `BLOCK_IP` executed against the attacker IP, *or* the open drill's current-step
  correct answer carried `ISOLATE_NETWORK`), the run's outcome becomes `contained` and
  every remaining cancellable phase is skipped. Phases without `cancel_if` still fire
  (an encrypt wave already running keeps going — that's the "act fast" lesson).
- Outcome states: `contained` / `spread` (all phases fired) / `stopped` (Backstage
  killed it) / `expired` (time limit, default 10 sim-minutes).

### 1.3 Engine: `ingest/simulator.py` (module, ~150 lines)

```
class Simulator:
    def __init__(self, script_path, db, clock, ingest_dir): ...
    def start(self, script_id) -> run_id        # creates the sim_runs row
    def stop(self)                              # Backstage kill switch
    def next_batch(self) -> list[RawAlert]      # AlertSource protocol: due phases only
    def outcome(self) -> dict                   # {id, script, status, phases_fired,
                                                #  phases_cancelled, elapsed_ms, reason}
```

- `next_batch()` returns the due phases as `RawAlert`s (`source: "wazuh"`,
  `external_id: "sim:{run}:{phase}"` — the pipeline's `external_id` dedupe handles
  ticks landing twice; `shieldmate` counts attached per phase).
- The 5 s ingest loop (`main._ingest_loop`) already calls `ctx.source.next_batch()`;
  a `SIMULATE` flag makes `build_context` prefer `Simulator` over `ReplaySource` for
  the live loop. Replay stays wired for the stage fallback — the two coexist, exactly
  like `ALERT_SOURCE` does today.
- Containment check: read-only joins over `actions` (executed `BLOCK_IP` matching
  `attacker.ip`) and the open drill's last-correct answer's `action_ids`. No writes —
  the sim *observes* the DB, it never mutates alerts or drill rows (those modules stay
  the only writers).

New schema (one table, appended to `schema.sql` + `RUNTIME_TABLES` so reset clears it):

```sql
CREATE TABLE sim_runs (
    id INTEGER PRIMARY KEY,
    script_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','contained','spread','stopped','expired')),
    outcome_reason TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
```

### 1.4 Backstage routes (contract additions — all four owners, one merge, T8.05)

| Route | Body / result |
|---|---|
| `POST /demo/simulate/{script_id}` | starts a run → `{"run_id", "script", "status": "running", "phases": N}` |
| `POST /demo/simulate/stop` | kills the current run → the outcome object |
| `GET /demo/simulate` | progress: `{"run_id", "status", "phase_now", "phases_fired", "elapsed_ms"}` (poll 2 s) |
| `POST /demo/reset` | already exists; gains "clears `sim_runs` + rewinds the sim" |

All backstage-token gated, like `/demo/*`. `GET /status` gains `"simulate": bool`
(flag on) so the UI hides the Simulate button when off.

### 1.5 The end-to-end story this buys (the "proper" part)

1. Backstage: **Simulate → ransom_wave**. T+0 Meena's phone: card *"Someone is
   repeatedly guessing the password on RECEPTION-PC"* with steps (the existing 60204
   lesson). T+90 s: *"first login succeeded"* — heads_up card, the situation changed,
   the sim is visibly advancing.
2. Owner taps **Practise this with the team** (the existing `drill_scenario` link) →
   drill opens from the *live* alert (`source_alert_id` — already in the schema).
3. Team answers. Correct contain (`ISOLATE_NETWORK`) by phase 3's deadline → the
   encrypt wave **never fires**. End screen: *Attack contained in 4:12 — 2 of 3 phases
   cancelled. Patient records never touched.* Wrong/slow answers → phase 3 fires,
   the impact meter (Feature 2) lights up **CRITICAL**, and the results screen shows
   the missed actions weighted by impact.
4. Backstage: Stop / Reset. No Wazuh was ever touched.

### 1.6 First three scripts (Cetas, content-only, same review as scenarios)

| Script | Phases | Teaches |
|---|---|---|
| `ransom_wave` (above) | storm → success → encrypt wave | isolate fast; backup check |
| `phish_owner` | mail-flag (new 61320 rule) → owner's PC → data exfil attempt (104104) | role-based impact: boss > reception |
| `credential_sprawl` | one PC's password → same password on two more devices (three 60204s, three agents) | one failure, three cards, grouping vs. new cards |

New rules need matching `lessons.json` entries first (61320, 104104 — English text
only, translations stay pending as today).

---

## Feature 2 — Impact priority (increment 7, gate T7; lands *before* sim so sim can
consume it)

### 2.1 Where the numbers come from (seed lookup, like the impact meter)

New seed block in `seed/clinic.json` (loader + validator, T0-style rules; no schema
change — the engine reads it straight, same as `lessons.json`):

```json
"impact": {
  "services": {"patient records": 5, "billing": 4, "appointments": 4,
               "consultations": 3, "front-desk check-in": 2},
  "accounts":  {"owner": 5, "billing": 3, "front_desk": 2},
  "damage":    {"encrypted": 3, "infected": 2, "compromised": 2, "isolated": 1, "ok": 0}
}
```

### 2.2 `alerts/impact.py` — pure function, one formula

```
impact(alert) = services_at_risk_weight × damage_state
           + account_weight(alert's compromised user/role)
```

Worked examples (the "boss vs receptionist" rule, made numeric):

| Situation | Score | Band | Why the team should read it this way |
|---|---|---|---|
| 60204 on RECEPTION-PC (frontdesk account) | 2×1 + 2 = 4 | **low** | check-in only; phone it, don't sprint |
| 60204 on FILE-SERVER *with* successful login | 13×1 + 3 = 16 | **high** | patient records reachable in one more step |
| 100201 on FILE-SERVER (files renamed) | 13×3 + 0 = 39 | **critical** | data being destroyed, not just threatened |
| Phish succeeds on Dr. Rao's PC | 3×2 + 5 = 11 | **high** | the most-privileged account, even though the machine is "only" consultations |

Bands: ≤4 low, ≤8 medium, ≤16 high, >16 critical. (Thresholds live in the seed block
so the team can tune without code.)

The reason string is generated, not free text: `"Critical — 39: patient records +
billing are being destroyed on FILE-SERVER"`. It feeds card copy, the strip, and the
drill results in one place, so it can't drift.

### 2.3 Surface (contract additions, T7.03–T7.07)

- `AlertOut` gains `impact: {level, score, reason} | null` (null for filtered noise —
  the filter keeps doing its job).
- `DeviceOut` (the owner strip) gains the same object, so a glance answers *how bad is
  it* next to *which device*.
- Owner queue ordering: `GET /alerts` sorts by `last_seen` today; it gains
  `?sort=impact` (default stays `time` — no behaviour change for existing pollers).
- Drill results: `PlayerResult.missed_actions` already exists; T7.06 makes
  `drills/scoring.py` carry the impact of each missed action through
  (`scoring.py` is Cetas's — natural fit), so "Team result" reads
  *"Most impact you skipped: patient records (39)."*
- Notification text for high/critical: `f"{staff} handled: [CRITICAL] …"` — one line,
  no new route.

### 2.4 Unit-gate tests (T7)

T7.01 seed block validates (weights positive, enum keys); T7.02 formula + all four
examples above as fixtures; T7.03 alert shape; T7.04 strip shape; T7.05 sort; T7.06
weighted results; T7.07 contract tests updated in the same merge (the frozen-contract
rule).

---

## Phases, owners, gates

| Phase | What | Owner | Gate | Est. |
|---|---|---|---|---|
| P1 | Impact: seed block, `alerts/impact.py`, contract+routes+UI badges, weighted scoring | Cetas (engine/scoring), Abhiram (badges, sorted queue) | **T7** | 2–3 d |
| P2 | Sim: script format + validator, `ingest/simulator.py`, `sim_runs`, backstage routes, 3 scripts | Ishaan (seam/engine), Cetas (scripts + lessons for 61320/104104) | **T8** | 3–4 d |
| P3 | Sim × drill handoff (live `source_alert_id` start), end-screen outcome copy, "contained in…" timer | Cetas + Abhiram | T8.08–T8.10 | 1–2 d |
| P4 | Lab: phased `attack.sh` reusing the same script format (`--auto`), sim outcome cross-checked against real indexer alerts | Kishaann | T8.11 | 1–2 d |

P1 before P2: the sim's end-screen *is* the impact meter (critical vs. contained), so
the priority number has to exist first. P4 last: it's the only phase that needs the VM.

## Hard rules (copy from the plans' ground rules)

1. Flags default off: `SIMULATE=0` until T8.10 passes on the demo rig; replay stays the
   stage fallback. An increment is done when its gate passes, not when the code is
   written.
2. The simulator is an `AlertSource`: it never writes `alerts`/`actions`/drill rows,
   never touches Wazuh (decision-12 safety rule), and its alerts are exactly
   `RawAlert`-shaped so the pipeline is untouched.
3. Determinism: sim time via `FakeClock`, no randomness, `sim_time_ms_multiplier` in
   the script. Two runs of the same script with the same answers → same cards, same
   times (T8.09).
4. Contract changes (T7.03–07, T8.05) follow the existing rule: all four owners,
   contract tests + fixtures updated in the same merge.
5. Sim scripts and new lessons are **content**: peer-reviewed like scenario files,
   English only until translations are scheduled.
6. If a phase slips, cut in order: P4 (lab) → P3 (handoff polish) → third script →
   `?sort=impact`. Never cut P2's `cancel_if` — that branch is the feature.

## Open questions (team, 15-minute meeting)

1. Sim multiplier for the live demo: 20× (9-min attack → 27 s) or 40×? Decide at T8.
2. Does the sim auto-start a drill at phase 1, or only on the owner's tap (current
   design: tap only — judges control the story)?
3. Impact threshold bands (2/8/16): Abhiram to sanity-check against the wireframe
   before T7.01, or does the team vote?
4. Who reviews sim scripts for clinic plausibility (same bar as the CERT-In/DPDP
   lines)? Suggested: Abhiram.
5. New rule lessons (61320, 104104) need two more English entries in `lessons.json`
   before P2's third script — same owner as `phish_owner`.
