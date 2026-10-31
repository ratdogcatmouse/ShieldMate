// Attack notifications on a phone: the cursor poll, the live block status and the button states.
// The logic is plain functions (tested in notifications.test.js); useNotifications wires them to usePoll.
import { useEffect, useRef } from "react";
import * as api from "./api.js";
import { fmtTime } from "./time.js";
import { usePoll } from "./usePoll.js";

const KEEP = 20;   // notes held on a phone; older ones scroll away

// The button on a note, from its quick_action. null = no button at all. The label of an
// active button is the server's own (never built here); the finished states are fixed text.
//   proposed -> active button | executed -> disabled "Blocked" | expired -> disabled "Block ended"
// Anything else (declined, withdrawn, ...) gets no button; the backend only attaches the three above.
export function blockButton(quickAction, expiresAt) {
  if (!quickAction) return null;
  switch (quickAction.status) {
    case "proposed": return { label: quickAction.label, disabled: false };
    case "executed": return { label: expiresAt ? `Blocked until ${fmtTime(expiresAt)}` : "Blocked", disabled: true };
    case "expired": return { label: "Block ended", disabled: true };
    default: return null;
  }
}

// One poll of GET /notifications, keeping the cursor. `fetchSince(id)` returns the response.
// The server answers with the newest id even when nothing is new, so a `last_id` that has
// dropped below our cursor means a Reset: forget everything and start again from 0.
export async function pollNotifications(state, fetchSince) {
  let { cursor, notes } = state;
  let res = await fetchSince(cursor);
  if (res.last_id < cursor) {
    cursor = 0;
    notes = [];
    res = await fetchSince(0);
  }
  const have = new Set(notes.map((n) => n.id));
  const fresh = res.notifications.filter((n) => !have.has(n.id));
  return { cursor: res.last_id, notes: [...notes, ...fresh].slice(-KEEP) };
}

// A note comes back from the server only once (the cursor), so its quick_action.status is
// frozen at "proposed". The live status of the block is on GET /actions, matched by
// action_row_id; that is also where "blocked until" (expires_at) comes from.
export function withLiveStatus(note, actions) {
  const qa = note.quick_action;
  if (!qa) return note;
  const act = actions.find((a) => a.id === qa.action_row_id);
  if (!act) return note;
  return { ...note, quick_action: { ...qa, status: act.status }, expiresAt: act.expires_at };
}

// The owner's lock-screen page already shows a pending block as its own approval card, so an
// attack note pointing at that same action would say the same thing twice.
export function hideBlockDuplicates(notes, actions) {
  const pending = new Set(actions.filter((a) => a.status === "proposed").map((a) => a.id));
  return notes.filter((n) => !(n.kind === "attack" && pending.has(n.action_row_id ?? n.quick_action?.action_row_id)));
}

// Notifications for one phone, newest last, each with its live block status.
// usePoll(...) -> {data: notes | null, refresh}. Pass role null to switch it off (person unknown yet).
export function useNotifications(role, staffId) {
  const held = useRef({ cursor: 0, notes: [] });
  // A different person on this page starts with a clean cursor (declared before usePoll so it runs first).
  useEffect(() => { held.current = { cursor: 0, notes: [] }; }, [role, staffId]);
  return usePoll(role ? async () => {
    held.current = await pollNotifications(held.current, (since) => api.getNotifications(role, staffId, since));
    const notes = held.current.notes;
    let actions = [];
    if (notes.some((n) => n.quick_action)) {
      // If /actions can't be read, fall back to each note's own status rather than hide the note.
      try { actions = await api.listOrEmpty(api.getActions(), "actions"); } catch { actions = []; }
    }
    return notes.map((n) => withLiveStatus(n, actions));
  } : null, 2000, [role, staffId]);
}
