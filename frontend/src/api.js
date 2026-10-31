// One function per route in backend/contract.py ROUTES, returning parsed JSON or throwing ApiError.
// VITE_API_MODE=mock|http (default mock). Mock mode serves backend/fixtures/*.json as they are.
import { getOwnerPin } from "./session.js";

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

async function http(method, path, { body, who } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  // Only sent when set; both stay empty while the owner PIN is off (decision 3).
  if (who === "owner") {
    const pin = getOwnerPin();
    if (pin) headers["X-Owner-Pin"] = pin;
  }
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "internal_error", "Can't reach the ShieldMate server.");
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    throw new ApiError(
      res.status,
      (data && data.error) || "internal_error",
      (data && data.message) || "Something went wrong.",
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
export const getAlerts = (role, lang) =>
  call("GET", `/alerts${query({ role, lang })}`, "alerts.json");
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
