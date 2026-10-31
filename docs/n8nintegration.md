# AI Interpreter — Chat with the n8n agent

Stuck on a ShieldMate task (attack / drill / simulation)? A floating "?" widget opens a small
chat box. Each question goes to a backend endpoint, which proxies to the n8n agent
(`https://kodikon.app.n8n.cloud/webhook/ai-agent-query`) and returns the answer. **Backend = Cetas,
Frontend = Ishaan.** Plan only — nothing is built until you say go.

## Core decision
Proxy through the backend (do NOT let the browser call n8n directly): the webhook URL stays
server-side (like Wazuh creds) and we send a **sanitized context object**, never raw alert text.
This mirrors the existing `actions/wazuh_client.py` real/fake seam and the `lessons/providers.py`
AI-provider seam — the two established "call an external thing" patterns in the repo.

---

## Cetas — Backend

### 1. Config flags (`backend/config.py`)
- `AI_INTERPRETER` (bool, default **off**) via the existing `_flag()` pattern; real env wins over `.env`.
- `AI_INTERPRETER_URL` (str, default the n8n webhook) + `AI_INTERPRETER_TIMEOUT_SECONDS` (int, default 30).
- Add to `Context` as `interpreter` (client) and `interpreter_enabled: bool`.

### 2. Client seam `backend/ai/interpreter.py` (mirror `wazuh_client.py` + `providers.py`)
- `InterpreterClient` Protocol: `def ask(self, question, context, role, lang) -> str`.
- `RealInterpreterClient(config)`: strict config check (URL present + https); POST
  `{question, context, role, lang}` to the n8n URL via stdlib `urllib` (strict TLS, reject
  redirects, 8MB cap, fixed timeout). n8n returns `{"text": ...}` or a string — parse defensively.
- `FakeInterpreterClient`: canned answer + records `.calls` (demos/tests).
- `get_interpreter(config)` → Fake if flag off or no URL; Real if enabled+URL set. A broken config
  must never take the app down (T5.09): `main.build_context` wraps construction in try/except,
  falls back to Fake, and `db.emit("system.source_fallback", ...)` — exactly like `wazuh`.
- Wire into `Context` + `main.build_context` the same way `reword_provider` is.

### 3. Sanitized context builder `backend/ai/context.py`
- `build_context(db, *, alert_id, drill_code, device_id, role, lang) -> dict`
- **Only ids/enums/short labels**: active alert (id, rule name, severity, state), current drill
  step (the shown step title/prompt — the sanctioned "task given" string, not raw logs), device
  (name), role, lang. Unknown/None id → omit that block. **Never** raw `log_fields` (reword T3.01).

### 4. Route `backend/routes/interpreter.py` (thin, mirror `routes/alerts.py::post_reword`)
- `POST /interpreter/chat`, gated by `Depends(require_flag("AI_INTERPRETER"))` → 404 `not_enabled`
  when off. `who="any"` (it's a help feature — staff/owner/backstage can all ask).
- Body: `InterpreterRequest { question (≤500), alert_id?, drill_code?, device_id?, role, lang }`.
  Build context → `ctx.interpreter.ask(...)` → `ctx.db.emit("interpreter.query", ...)`.
  Return `InterpreterResponse { answer (≤2000), source: "ai" | "fallback" }`.
- Fallback on any real-client exception: return the current alert/drill's plain-language headline
  from db, `source="fallback"` (mirror the reword guard's fallback; a dead n8n never 500s).
- Register in `main.py`: add `"interpreter"` to `LANE_TWO_ROUTERS` (Cetas's lane).

### 5. Contract (`backend/contract.py`) — ships in the same merge as fixtures + test
- `InterpreterRequest` / `InterpreterResponse` models.
- `Route(method="POST", path="/interpreter/chat", request=..., response=..., who="any",
  flag="AI_INTERPRETER")`.
- `EXTRA_FIXTURES` + `fixtures/interpreter.json`; a `test_contract.py` case (route exists + flag
  gate → `not_enabled`).

### 6. Event log
- Add `interpreter.query` to `eventlog/catalogue.py` `EVENT_TYPES` (payload: ids/enums only).
  `db.emit` in the route.

### 7. Tests (`backend/tests/unit/` + a route test)
- fake → canned answer + `interpreter.query` emitted; flag off → 404; real-client exception →
  `source="fallback"`. Keep the suite green (last full run 389 passed).

---

## Ishaan — Frontend

### 1. `frontend/src/lib/api.js`
- `export const chatInterpreter = (question, ctx) => call("POST", "/interpreter/chat", { body: {...} })`,
  attaching the current `alert_id` / `drill_code` / `device_id` + role/lang from page state,
  `session.js`, `derive.js`. (Add next to the other one-function-per-route entries.)

### 2. Widget `frontend/src/components/HelpWidget.jsx` (+ css)
- Fixed floating "?" button (bottom-right) on the task screens: `OwnerNotify.jsx`, `OwnerDrill.jsx`,
  `StaffDrill.jsx`, `Mission.jsx` (attack + drill + simulation surfaces).
- Click → opens a ~320px chat box (message list + input + send). Local `useState` holds the
  conversation; on each send, attach "what I'm looking at" context from the page.
- Multi-turn: keep the last few messages client-side and pass them as a short `history` array in the
  request body — server stays stateless.
- Handle `not_enabled` ("AI help isn't enabled here"), server errors, and fallback answers like any
  normal reply.

### 3. Telemetry (`lib/telemetry.js`)
- `track("ui.help_widget_open")` on open; `track("ui.help_question", { alert_id, drill_code, role })`
  on send.

---

## Decisions baked in (change on approval if you disagree)
- **Proxy via backend**, not browser→n8n (keeps the webhook URL server-side; sanitized context).
- **Flag `AI_INTERPRETER` off by default** — feature ships inert until enabled, matching the flag pattern.
- **Stateless multi-turn** — history rides in the request body; no backend session store.
- **Gating `who="any"`** behind the flag (any role can ask), not owner-only.

## Order of work
1. Cetas: flags + seam + context + route + contract + event + tests (one backend merge, off by default).
2. Ishaan: api.js + widget + telemetry.
3. Turn on via `.env` (`AI_INTERPRETER=1`, URL set) → smoke-test end-to-end.
