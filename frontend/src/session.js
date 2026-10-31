// Who this device is and which drill it joined. Every storage access is wrapped:
// Safari private mode (and blocked storage) can throw on read or write.
const KEYS = {
  staff: "sm.staff",
  lang: "sm.lang",
  drill: "sm.drill",
  notifSince: "sm.notif_since",
  ownerPin: "sm.owner_pin", // sessionStorage: cleared when the tab closes
  session: "sm.session", // sessionStorage: one id per tab for the event log
  backstageToken: "sm.backstage_token", // sessionStorage: only needed once BACKSTAGE_TOKEN is set
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

function readJson(key) {
  const raw = read("localStorage", key);
  if (raw === null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

// {id, name, role} for a person, or the string "backstage".
export const getStaff = () => readJson(KEYS.staff);
export const setStaff = (staff) => write("localStorage", KEYS.staff, JSON.stringify(staff));
export const clearStaff = () => write("localStorage", KEYS.staff, null);

export function getLang() {
  const lang = read("localStorage", KEYS.lang);
  return lang === "kn" || lang === "hi" ? lang : "en";
}
export const setLang = (lang) => write("localStorage", KEYS.lang, lang);

// {code, player_id}
export const getDrill = () => readJson(KEYS.drill);
export const setDrill = (drill) => write("localStorage", KEYS.drill, JSON.stringify(drill));
export const clearDrill = () => write("localStorage", KEYS.drill, null);

export function getNotifSince() {
  const n = Number(read("localStorage", KEYS.notifSince));
  return Number.isFinite(n) && n > 0 ? n : 0;
}
export const setNotifSince = (id) => write("localStorage", KEYS.notifSince, String(id));
export const clearNotifSince = () => write("localStorage", KEYS.notifSince, null);

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
