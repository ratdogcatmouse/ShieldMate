import { useSyncExternalStore } from "react";

// The server's clock, not the phone's: Backstage's "Skip 5 min" moves the server forward, and
// countdowns ("blocks at 10:15", "5 h 38 min left") must agree with what the server will do.
// App.jsx calls syncServerTime with GET /status's server_time every few seconds.
let offsetMs = 0;
export function syncServerTime(iso) {
  const t = Date.parse(iso);
  if (Number.isFinite(t)) offsetMs = t - Date.now();
}
export const serverNow = () => Date.now() + offsetMs;

// One shared 1-second ticker for every countdown on the page.
const listeners = new Set();
let ticker = null;
function subscribe(fn) {
  listeners.add(fn);
  if (!ticker) ticker = setInterval(() => listeners.forEach((l) => l()), 1000);
  return () => {
    listeners.delete(fn);
    if (!listeners.size) {
      clearInterval(ticker);
      ticker = null;
    }
  };
}
const snapshot = () => Math.floor(serverNow() / 1000);

// Re-renders the caller every second; returns the server's "now" in ms.
export function useNow() {
  useSyncExternalStore(subscribe, snapshot, snapshot);
  return serverNow();
}

// --- formatting (the API sends ISO 8601 UTC with Z; the clinic reads Indian time) ---

export const toMs = (iso) => (iso ? Date.parse(iso) : null);

export function fmtTime(iso) {
  if (!iso) return "";
  return new Date(typeof iso === "number" ? iso : Date.parse(iso))
    .toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" })
    .replace(/\s?(am|pm)$/i, (m) => ` ${m.trim().toUpperCase()}`);
}

export function fmtDate(ms) {
  return new Date(ms).toLocaleDateString("en-IN", {
    weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Kolkata",
  });
}

// "just now", "4 min ago", "1 h 5 min ago"
export function ago(iso, now = serverNow()) {
  const m = Math.max(0, Math.round((now - toMs(iso)) / 60000));
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  return `${Math.floor(m / 60)} h ${m % 60} min ago`;
}

// "5 h 38 min left"
export function left(ms, now = serverNow()) {
  const m = Math.max(0, Math.round((ms - now) / 60000));
  return `${Math.floor(m / 60)} h ${m % 60} min left`;
}

// 4:05
export function mmss(sec) {
  const s = Math.max(0, sec | 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// 04:05 (the mission-control stopwatch)
export function stopwatch(sec) {
  const s = Math.max(0, sec | 0);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

// The hour of day in the clinic, for "Good morning".
export function clinicHour(ms = serverNow()) {
  return Number(new Date(ms).toLocaleString("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }));
}
