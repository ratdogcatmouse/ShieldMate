// What this device remembers. Every storage access is wrapped: Safari private mode (and
// blocked storage) can throw on read or write, and the app must still work without it.
const KEYS = {
  lang: "sm.lang",
  ownerPin: "sm.owner_pin", // sessionStorage: cleared when the tab closes
  session: "sm.session", // sessionStorage: one id per tab for the event log
  backstageToken: "sm.backstage_token", // sessionStorage: only needed once BACKSTAGE_TOKEN is set
  resetId: "sm.reset_id", // localStorage: the server's reset_id this device last saw
};

function read(store, key) {
  try {
    return window[store].getItem(key);
  } catch {
    return null;
  }
}

function write(store, key, value) {
  try {
    if (value === null || value === undefined) window[store].removeItem(key);
    else window[store].setItem(key, value);
  } catch {
    /* storage unavailable: carry on without persistence */
  }
}

// The staff card's language. Kannada and Hindi fall back to English per string on the server.
export function getLang() {
  const lang = read("localStorage", KEYS.lang);
  return lang === "kn" || lang === "hi" ? lang : "en";
}
export const setLang = (lang) => write("localStorage", KEYS.lang, lang);

// This device's player id in a drill. Joining again returns the same id (decision 14), but a
// finished drill refuses joins, so the id is kept to show the results.
const playerKey = (code, staffId) => `sm.player.${code}.${staffId}`;
export function getPlayer(code, staffId) {
  const n = Number(read("localStorage", playerKey(code, staffId)));
  return Number.isInteger(n) && n > 0 ? n : null;
}
export const setPlayer = (code, staffId, playerId) =>
  write("localStorage", playerKey(code, staffId), String(playerId));

// The owner's last drill, for the Readiness page's "team practice" card.
export const getLastDrill = () => read("localStorage", "sm.last_drill");
export const setLastDrill = (code) => write("localStorage", "sm.last_drill", code);

// Once per tab: has this alert (or IT ticket, or approval request) already buzzed?
// `key` is a short string; sessionStorage so a new tab buzzes again.
// Kept in memory too, so it still works once per page load when storage throws.
const memorySeen = new Set();
export function seenOnce(key) {
  const k = `sm.seen.${key}`;
  if (memorySeen.has(k) || read("sessionStorage", k)) return true;
  memorySeen.add(k);
  write("sessionStorage", k, "1");
  return false;
}

// Clears the per-tab "already seen" marks (Backstage Reset), so the next demo buzzes again.
export function clearSeen() {
  memorySeen.clear();
  try {
    Object.keys(window.sessionStorage)
      .filter((k) => k.startsWith("sm.seen."))
      .forEach((k) => window.sessionStorage.removeItem(k));
  } catch {
    /* nothing to clear */
  }
}

// The server's reset_id (from /status) changes on every reset or fresh database. When it does,
// forget this device's drill players, last drill, owner PIN and seen marks so the next demo
// starts clean. Language, the event-log session and the Backstage token are kept.
// Returns true when there was an older id and it changed (the caller reloads the page).
export function syncResetId(id) {
  if (!id) return false;
  const prev = read("localStorage", KEYS.resetId);
  if (prev === id) return false;
  try {
    Object.keys(window.localStorage)
      .filter((k) => k.startsWith("sm.player.") || k === "sm.last_drill")
      .forEach((k) => window.localStorage.removeItem(k));
  } catch {
    /* nothing to clear */
  }
  write("sessionStorage", KEYS.ownerPin, null);
  clearSeen();
  write("localStorage", KEYS.resetId, id);
  // Only reload when the new id actually stuck, so blocked storage can't cause a reload loop.
  return prev !== null && read("localStorage", KEYS.resetId) === id;
}

export const getOwnerPin = () => read("sessionStorage", KEYS.ownerPin);
export const setOwnerPin = (pin) => write("sessionStorage", KEYS.ownerPin, pin);

// Sent as X-Backstage-Token on /demo/* calls. Empty while the server's BACKSTAGE_TOKEN is unset.
export const getBackstageToken = () => read("sessionStorage", KEYS.backstageToken);
export const setBackstageToken = (token) => write("sessionStorage", KEYS.backstageToken, token || null);

// The event log's session: a reload keeps it, a new tab gets a new one. Kept in memory too,
// for when storage throws. Hex from getRandomValues, because crypto.randomUUID needs HTTPS
// and the demo runs over plain http on the hotspot.
let memorySession = null;
export function getSessionId() {
  let id = read("sessionStorage", KEYS.session) || memorySession;
  if (!id) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    id = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    write("sessionStorage", KEYS.session, id);
  }
  memorySession = id;
  return id;
}
