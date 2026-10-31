// Who this device is and which drill it joined. Every storage access is wrapped:
// Safari private mode (and blocked storage) can throw on read or write.
const KEYS = {
  staff: "sm.staff",
  lang: "sm.lang",
  drill: "sm.drill",
  notifSince: "sm.notif_since",
  ownerPin: "sm.owner_pin", // sessionStorage: cleared when the tab closes
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
