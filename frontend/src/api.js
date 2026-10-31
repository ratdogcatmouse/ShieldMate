// One function per route in backend/contract.py ROUTES, returning parsed JSON or throwing ApiError.
// VITE_API_MODE=mock|http (default mock). Mock mode serves backend/fixtures/*.json as they are.
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

export const API_MODE = import.meta.env.VITE_API_MODE === "http" ? "http" : "mock";

const fixtures = import.meta.glob("../../backend/fixtures/*.json", {
  eager: true,
  import: "default",
});

function fixture(name) {
  const body = fixtures[`../../backend/fixtures/${name}`];
  if (body === undefined) throw new ApiError(500, "internal_error", `Missing fixture ${name}`);
  return structuredClone(body);
}

function query(params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) q.set(k, String(v));
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

async function http(method, path, { body, who } = {}) {
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

// `mock` is the fixture file for this route (the same one ROUTES names).
async function call(method, path, mock, opts) {
  if (API_MODE === "mock") return fixture(mock);
  return http(method, path, opts);
}

export const getClinic = () => call("GET", "/clinic", "clinic.json");
export const getStatus = () => call("GET", "/status", "status.json");
// sort: "time" (default, newest first) or "impact" (highest impact score first).
export const getAlerts = (role, lang, sort) =>
  call("GET", `/alerts${query({ role, lang, sort })}`, "alerts.json");
export const markDone = (id, staffId) =>
  call("POST", `/alerts/${id}/done`, "alert_done.json", { body: { staff_id: staffId } });
export const reword = (id, role, lang) =>
  call("POST", `/alerts/${id}/reword`, "reword.json", { body: { role, lang } });
export const getNotifications = (role, staffId, sinceId) =>
  call(
    "GET",
    `/notifications${query({ role, staff_id: staffId, since_id: sinceId })}`,
    "notifications.json",
  );

export const createDrill = (scenarioId, hostStaffId, sourceAlertId = null) =>
  call("POST", "/drills", "drill_create.json", {
    who: "owner",
    body: { scenario_id: scenarioId, host_staff_id: hostStaffId, source_alert_id: sourceAlertId },
  });
export const joinDrill = (code, staffId) =>
  call("POST", `/drills/${code}/join`, "drill_join.json", { body: { staff_id: staffId } });
export const getDrill = (code, playerId) =>
  call("GET", `/drills/${code}${query({ player_id: playerId })}`, "drill_view.json");
export const answer = (code, playerId, stepId, optionId) =>
  call("POST", `/drills/${code}/answers`, "drill_answer.json", {
    body: { player_id: playerId, step_id: stepId, option_id: optionId },
  });
export const advance = (code, playerId) =>
  call("POST", `/drills/${code}/advance`, "drill_view_review.json", {
    who: "owner",
    body: { player_id: playerId },
  });

export const runRestore = () =>
  call("POST", "/restore/run", "restore_run.json", { who: "owner" });
export const getRestoreLatest = () => call("GET", "/restore/latest", "restore_latest.json");

// Flag ACTIONS: a flagged-off route answers not_enabled (404).
export const getDevices = () => call("GET", "/devices", "devices.json");
export const getActions = (status) =>
  call("GET", `/actions${query({ status })}`, "actions.json");
export const approve = (id, staffId) =>
  call("POST", `/actions/${id}/approve`, "action_executed.json", {
    who: "owner",
    body: { staff_id: staffId },
  });
export const decline = (id, staffId) =>
  call("POST", `/actions/${id}/decline`, "action_declined.json", {
    who: "owner",
    body: { staff_id: staffId },
  });
export const undo = (id, staffId) =>
  call("POST", `/actions/${id}/undo`, "action_undone.json", {
    who: "owner",
    body: { staff_id: staffId },
  });
export const setStandingRule = (enabled, staffId) =>
  call("PUT", "/clinic/standing-rule", "standing_rule.json", {
    who: "owner",
    body: { enabled, staff_id: staffId },
  });

export const replay = (type) =>
  call("POST", `/demo/replay/${type}`, "demo_replay.json", { who: "backstage" });
export const reset = () => call("POST", "/demo/reset", "demo_reset.json", { who: "backstage" });

// Flag SIMULATE: the in-app attacker. Flagged off, these answer not_enabled (404).
export const simulateStart = (scriptId) =>
  call("POST", `/demo/simulate/${scriptId}`, "demo_simulate_start.json", { who: "backstage" });
export const simulateStop = () =>
  call("POST", "/demo/simulate/stop", "demo_simulate_stop.json", { who: "backstage" });
export const getSimulate = () =>
  call("GET", "/demo/simulate", "demo_simulate_status.json", { who: "backstage" });

// Flag EVENT_LOG. Called by telemetry.js only (startTelemetry in main.jsx plugs it in).
export const postEvents = (sessionId, events) =>
  call("POST", "/events", "events_accepted.json", { body: { session_id: sessionId, events } });
