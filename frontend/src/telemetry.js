// UI events for the server's event log (POST /api/events). The types and the data keys each
// may carry are listed in backend/eventlog/catalogue.py; anything else is dropped there.
// `data` holds ids, enums and codes only: never on-screen text, log fields or the owner PIN.
// Nothing here may break a tap: every failure is swallowed and the event is lost.
import { getSessionId, getStaff } from "./session.js";

const FLUSH_MS = 5000;
const FLUSH_AT = 20;   // send early once this many are waiting
const BATCH = 50;      // the route's limit per request
const MAX_QUEUE = 200; // offline for a while: keep the newest only

let queue = [];
let send = null;       // api.js postEvents, plugged in by startTelemetry
let stopped = false;   // mock mode, or the server answered not_enabled
let flushing = false;

// Who the page is acting as: the staff id in /staff/:id, else the person picked on Start.
// Backstage stores the string "backstage", which is nobody.
function pageStaffId() {
  const m = window.location.pathname.match(/^\/staff\/(\d+)/);
  if (m) return Number(m[1]);
  const staff = getStaff();
  return staff && typeof staff === "object" ? staff.id ?? null : null;
}

export function track(type, data = {}, staffId = pageStaffId()) {
  if (stopped) return;
  try {
    queue.push({
      type,
      client_ts: new Date().toISOString(),
      path: window.location.pathname,
      staff_id: staffId,
      data,
    });
    if (queue.length > MAX_QUEUE) queue = queue.slice(-MAX_QUEUE);
    if (queue.length >= FLUSH_AT) flush();
  } catch {
    /* never let telemetry break the app */
  }
}

async function flush() {
  if (stopped || !send || flushing || queue.length === 0) return;
  flushing = true;
  const batch = queue.splice(0, BATCH);
  try {
    await send(getSessionId(), batch);
  } catch (e) {
    if (e?.error === "not_enabled") {
      stopped = true; // EVENT_LOG=0 on the server: stop for this page load
      queue = [];
    } else if (e?.status === 0) {
      queue = [...batch, ...queue].slice(-MAX_QUEUE); // offline: try again next time
    } // anything else means the batch itself was refused, so it is dropped
  } finally {
    flushing = false;
  }
}

// The tab is going away: a normal fetch may be cancelled, a beacon is not (but can't set headers,
// which is why the session id travels in the body).
function beacon() {
  if (stopped || queue.length === 0 || !navigator.sendBeacon) return;
  const batch = queue.splice(0, BATCH);
  try {
    const body = new Blob([JSON.stringify({ session_id: getSessionId(), events: batch })], {
      type: "application/json",
    });
    if (!navigator.sendBeacon("/api/events", body)) queue = [...batch, ...queue];
  } catch {
    /* lost */
  }
}

// `sender` is api.js postEvents, or null in mock mode (nothing is ever sent).
export function startTelemetry(sender) {
  if (!sender) {
    stopped = true;
    queue = [];
    return;
  }
  if (send) return;
  send = sender;
  setInterval(flush, FLUSH_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") beacon();
  });
  window.addEventListener("pagehide", beacon);
  window.addEventListener("error", (e) =>
    track("ui.app_error", { message: String(e.message || "error"), source: "error" }),
  );
  window.addEventListener("unhandledrejection", (e) =>
    track("ui.app_error", { message: String(e.reason?.message || e.reason || "rejected"), source: "promise" }),
  );
}
