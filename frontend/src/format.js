// The frontend shows Indian time; the API sends ISO 8601 UTC with Z.
export function fmtTime(iso) {
  if (!iso) return "";
  return new Date(iso)
    .toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" })
    .replace(/\s?(am|pm)$/i, (m) => ` ${m.trim().toUpperCase()}`);
}

export function mmss(sec) {
  const s = Math.max(0, sec | 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export const ROLE_LABEL = { front_desk: "Front desk", billing: "Billing", owner: "Owner" };
