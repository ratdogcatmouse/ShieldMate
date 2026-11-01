// One function per route in backend/contract.py ROUTES (contract v2), returning parsed JSON
// or throwing ApiError. Every call goes to the FastAPI backend under /api: `npm run dev`
// proxies it to localhost:8000, and in production FastAPI serves this app itself.
import { getBackstageToken, getOwnerPin, getSessionId } from "./session.js";
import { track } from "./telemetry.js";

export class ApiError extends Error {
  constructor(status, error, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.error = error;
    this.message = message;
  }
}

function query(params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== false) q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

// Failed calls go to the event log, once per route and error every 30 s: during an outage the
// 2 s polls would otherwise report the same failure over and over. The log's own route is skipped.
const lastReported = new Map();
function failed(method, path, err) {
  const route = path.split("?")[0]; // the query can carry ids and cursors; the path is enough
  const key = `${method} ${route} ${err.status} ${err.error}`;
  const now = Date.now();
  if (route !== "/events" && !(now - (lastReported.get(key) || 0) < 30000)) {
    lastReported.set(key, now);
    track("ui.api_error", { method, route, status: err.status, error: err.error });
  }
  return err;
}

async function call(method, path, { body, who } = {}) {
  // The session id lets the server's events for this call be matched to this tab's UI events.
  const headers = { "X-Session-Id": getSessionId() };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  // Only sent when set; both stay empty while the owner PIN is off (decision 3).
  if (who === "owner") {
    const pin = getOwnerPin();
    if (pin) headers["X-Owner-Pin"] = pin;
  }
  // /demo/* calls need the backstage token once the server has BACKSTAGE_TOKEN set.
  if (who === "backstage") {
    const token = getBackstageToken();
    if (token) headers["X-Backstage-Token"] = token;
  }
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw failed(method, path, new ApiError(0, "internal_error", "Can't reach the ShieldMate server."));
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    throw failed(
      method,
      path,
      new ApiError(
        res.status,
        (data && data.error) || "internal_error",
        (data && data.message) || "Something went wrong.",
      ),
    );
  }
  return data;
}

// --- clinic and status ---
export const getClinic = () => call("GET", "/clinic");
export const getStatus = () => call("GET", "/status");

// --- alerts ---
// role: front_desk | billing | owner. includeClosed adds incidents the owner has closed.
export const getAlerts = (role, { lang, sort, includeClosed } = {}) =>
  call("GET", `/alerts${query({ role, lang, sort, include_closed: includeClosed })}`);
export const markDone = (id, staffId, lang) =>
  call("POST", `/alerts/${id}/done${query({ lang })}`, { body: { staff_id: staffId } });
export const reword = (id, role, lang) =>
  call("POST", `/alerts/${id}/reword`, { body: { role, lang } });
// AI interpreter (flag AI_INTERPRETER, else not_enabled): the n8n agent explains what is on a card.
// body: { question (<=500), role, lang, alert_id? }. Answers { answer, source: "ai" | "fallback" }.
export const interpret = (body) => call("POST", "/interpreter/chat", { body });
// v2: tick or untick one card step, by action ID.
export const setStep = (id, action, staffId, done, lang) =>
  call("PUT", `/alerts/${id}/steps/${action}${query({ lang })}`, { body: { staff_id: staffId, done } });
// v2: "That was me" pauses the alert for an hour; reopen undoes it.
export const sayMine = (id, staffId, lang) =>
  call("POST", `/alerts/${id}/mine${query({ lang })}`, { body: { staff_id: staffId } });
export const reopen = (id, staffId, lang) =>
  call("POST", `/alerts/${id}/reopen${query({ lang })}`, { body: { staff_id: staffId } });
// v2: the IT contact's panel. action: received | note | resolved (resolved needs a 5+ character note).
export const itAction = (id, action, note = "") =>
  call("POST", `/alerts/${id}/it`, { body: { action, note } });
// v2: the owner checks IT's fix. confirm=false sends it back with `note` as the reason.
export const closeIncident = (id, staffId, confirm, note = "") =>
  call("POST", `/alerts/${id}/close`, { who: "owner", body: { staff_id: staffId, confirm, note } });

export const getNotifications = (role, staffId, sinceId) =>
  call("GET", `/notifications${query({ role, staff_id: staffId, since_id: sinceId })}`);

// --- drills ---
export const getCurrentDrill = () => call("GET", "/drills/current");
export const createDrill = (scenarioId, hostStaffId, sourceAlertId = null) =>
  call("POST", "/drills", {
    who: "owner",
    body: { scenario_id: scenarioId, host_staff_id: hostStaffId, source_alert_id: sourceAlertId },
  });
export const joinDrill = (code, staffId) =>
  call("POST", `/drills/${code}/join`, { body: { staff_id: staffId } });
export const getDrill = (code, playerId) =>
  call("GET", `/drills/${code}${query({ player_id: playerId })}`);
export const answer = (code, playerId, stepId, optionId) =>
  call("POST", `/drills/${code}/answers`, {
    body: { player_id: playerId, step_id: stepId, option_id: optionId },
  });
export const advance = (code, playerId) =>
  call("POST", `/drills/${code}/advance`, { who: "owner", body: { player_id: playerId } });
export const endDrill = (code, playerId) =>
  call("POST", `/drills/${code}/end`, { who: "owner", body: { player_id: playerId } });

// --- restore check ---
export const runRestore = () => call("POST", "/restore/run", { who: "owner" });
export const getRestoreLatest = () => call("GET", "/restore/latest");

// --- v3 restore-incident loop (a "not safe" check becomes an IT incident) ---
// IT polls the list (no who), marks it resolved with a note; only the owner closes it
// (confirm=true after a safe retest) or sends it back (confirm=false).
export const getRestoreIncidents = () => call("GET", "/restore/incidents");
export const resolveRestoreIncident = (note) =>
  call("POST", "/restore/incidents/resolve", { body: { note } });
export const closeRestoreIncident = (staffId, confirm, note = "") =>
  call("POST", "/restore/incidents/close", { who: "owner", body: { staff_id: staffId, confirm, note } });

// --- devices and actions (flag ACTIONS: a flagged-off route answers not_enabled, 404) ---
export const getDevices = () => call("GET", "/devices");
export const getActions = (status) => call("GET", `/actions${query({ status })}`);
export const approve = (id, staffId) =>
  call("POST", `/actions/${id}/approve`, { who: "owner", body: { staff_id: staffId } });
export const decline = (id, staffId) =>
  call("POST", `/actions/${id}/decline`, { who: "owner", body: { staff_id: staffId } });
export const undo = (id, staffId) =>
  call("POST", `/actions/${id}/undo`, { who: "owner", body: { staff_id: staffId } });
export const setStandingRule = (enabled, staffId) =>
  call("PUT", "/clinic/standing-rule", { who: "owner", body: { enabled, staff_id: staffId } });

// --- demo (Backstage) ---
export const replay = (type) => call("POST", `/demo/replay/${type}`, { who: "backstage" });
export const reset = () => call("POST", "/demo/reset", { who: "backstage" });
export const skip = (minutes) => call("POST", "/demo/skip", { who: "backstage", body: { minutes } });
// Flag SIMULATE: the in-app attacker. Flagged off, these answer not_enabled (404).
export const simulateStart = (scriptId) => call("POST", `/demo/simulate/${scriptId}`, { who: "backstage" });
export const simulateStop = () => call("POST", "/demo/simulate/stop", { who: "backstage" });
export const getSimulate = () => call("GET", "/demo/simulate", { who: "backstage" });

// Flag EVENT_LOG. Called by telemetry.js only (startTelemetry in main.jsx plugs it in).
export const postEvents = (sessionId, events) =>
  call("POST", "/events", { body: { session_id: sessionId, events } });

// A list route answers {"key": [...]}; flagged-off routes (not_enabled) read as empty, so a
// screen can show the parts that work instead of failing as a whole.
export async function listOrEmpty(promise, key) {
  try {
    return (await promise)[key];
  } catch (e) {
    if (e instanceof ApiError && e.error === "not_enabled") return [];
    throw e;
  }
}
