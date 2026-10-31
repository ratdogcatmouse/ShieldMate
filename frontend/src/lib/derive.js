// Facts the screens work out from API data, shared so the owner page, the IT panel and
// mission control always agree.
import { CERTIN_HOURS, DEVICE_STATUS, SCENARIOS, deviceShort } from "./content.js";
import { toMs } from "./time.js";

export const ownerOf = (clinic) => clinic.staff.find((s) => s.role === "owner") || null;
export const staffName = (clinic, id) => clinic.staff.find((s) => s.id === id)?.name ?? "Someone";

const isOpen = (a) => !a.it.closed_at;
export const passwordAlert = (alerts) => alerts.find((a) => a.lesson_id === "password_guessing" && isOpen(a)) || null;
export const ransomwareAlert = (alerts) =>
  alerts.find((a) => a.lesson_id === "ransomware" && isOpen(a) && a.status !== "mine") || null;

const stepDone = (alert, action) => !!alert?.card.steps.find((s) => s.action === action && s.done);

// The device strip. `apiDevices` is GET /devices (null when ACTIONS is off: then every PC
// starts OK and an open password alert marks its PC under attack). An open ransomware alert
// shows its PC as "files locked", or "cut off, still on" once someone ticked ISOLATE_NETWORK.
export function deviceStates(clinic, apiDevices, alerts) {
  const byAgent = Object.fromEntries((apiDevices || []).map((d) => [d.agent_name, d]));
  const pw = passwordAlert(alerts);
  const rw = ransomwareAlert(alerts);
  return clinic.devices.map((d) => {
    const live = byAgent[d.agent_name];
    let status = live ? live.status : pw && pw.status === "new" && pw.agent_name === d.agent_name ? "under_attack" : "ok";
    if (rw && rw.agent_name === d.agent_name) status = stepDone(rw, "ISOLATE_NETWORK") ? "isolated" : "files_locked";
    return {
      agent: d.agent_name,
      short: deviceShort(d.agent_name),
      location: d.location,
      status,
      ...DEVICE_STATUS[status],
      block: live?.block ?? null,
    };
  });
}

// CERT-In deadline (ms) for an incident whose lesson needs one, else null.
export function certinDue(alert) {
  const h = CERTIN_HOURS[alert.lesson_id];
  return h ? toMs(alert.first_seen) + h * 3600 * 1000 : null;
}

// The drill that practises this alert: the lesson's own, else a scenario named after it.
export function drillFor(alert) {
  if (alert.card.drill_scenario) return alert.card.drill_scenario;
  return SCENARIOS.some((s) => s.id === alert.lesson_id) ? alert.lesson_id : null;
}

// The approval deadline of a pending block (ISO), from the clinic's wait.
export function decideBy(action, clinic) {
  return new Date(toMs(action.proposed_at) + clinic.clinic.approval_timeout_minutes * 60000).toISOString();
}

// What IT said fixed it: the latest "resolved" note in the incident's history.
export const fixNote = (alert) =>
  [...alert.it.log].reverse().find((l) => l.kind === "resolved")?.note ?? "";

// The restore check counts for this incident only if it ran after the alert started.
export const restoreSince = (restore, alert) =>
  restore && restore.result !== "NOT_TESTED" && toMs(restore.started_at) >= toMs(alert.first_seen) ? restore : null;

const LIVE_WHAT = { password_guessing: "Password guessing", ransomware: "Ransomware" };

// The feed line for an alert that came from Wazuh (source "wazuh"), tagged so it can't be mistaken
// for a replay: "rule 60204 - Password guessing on RECEPTION-PC from 192.168.137.50 x9". One line per
// alert, however many times it repeats. The attacker's address is on the owner's card, else on the block request.
function liveLine(a, actions, fallback) {
  const ip = a.card.log_fields?.source_ip || actions.find((x) => x.alert_id === a.id)?.target_ip || null;
  const what = LIVE_WHAT[a.lesson_id] ? `${LIVE_WHAT[a.lesson_id]} on ${a.agent_name}` : fallback;
  const times = (a.count ?? 0) > 1 ? ` ×${a.count}` : "";
  return { tag: "LIVE · Wazuh", text: `rule ${a.rule_id} — ${what}${ip ? ` from ${ip}` : ""}${times}` };
}

// What happened, newest first: a timeline built from the timestamps the API already returns
// (alerts, block requests and decisions, ticked steps, the IT history) plus the owner's
// notifications. `alerts` should be the owner's view, with closed incidents included.
export function activity(clinic, alerts, actions, notes) {
  const it = clinic.clinic.it_contact_name;
  const who = (id) => (id === null ? it : staffName(clinic, id));
  const short = (a) => a.card.headline.replace(/\.$/, "");
  const ev = [];
  for (const a of alerts) {
    ev.push({ at: a.first_seen, ...(a.source === "wazuh" ? liveLine(a, actions, short(a)) : { text: short(a) }) });
    if (a.mine_at) ev.push({ at: a.mine_at, text: `${staffName(clinic, a.mine_by)} said "That was me"` });
    for (const s of a.card.steps) {
      if (s.done && s.action !== "CALL_SAVED_IT") ev.push({ at: s.done_at, text: `${staffName(clinic, s.done_by)}: ${s.text.replace(/\.$/, "")}` });
    }
    for (const l of a.it.log) {
      const text = { called: `${who(l.by_staff_id)} called ${it}`, received: `${it} picked it up`, note: `${it} added a note`,
        resolved: `${it} says it's fixed`, confirmed: "Owner confirmed the fix. Incident closed", sent_back: "Owner sent it back to IT" }[l.kind];
      ev.push({ at: l.at, text });
    }
  }
  for (const x of actions) {
    if (x.status === "refused") { ev.push({ at: x.proposed_at, text: `No block proposed: ${x.refused_reason}` }); continue; }
    ev.push({ at: x.proposed_at, text: `ShieldMate asked to block ${x.target_ip}` });
    if (x.decided_at) {
      const text = { executed: `Blocked ${x.target_ip}${x.decided_via === "standing_rule" ? " under the standing rule" : ""}`,
        expired: `Blocked ${x.target_ip}`, undone: `Blocked ${x.target_ip}`, declined: `Block on ${x.target_ip} declined`,
        failed: `Block on ${x.target_ip} didn't take effect` }[x.status];
      if (text) ev.push({ at: x.decided_at, text });
    }
  }
  // An attack note repeats its alert's own line above (same headline), so only the plain ones count.
  for (const n of notes) if (n.kind !== "attack") ev.push({ at: n.created_at, text: n.text });
  return ev.sort((a, b) => toMs(b.at) - toMs(a.at));
}

// "Recorded alerts · replay mode" / "Live · Wazuh connected" / "Wazuh not reachable".
export function sourceBadge(status) {
  if (!status || status.alert_source !== "wazuh") return { tone: "blue", text: "Recorded alerts · replay mode" };
  return status.wazuh.api_ok === false || status.wazuh.indexer_ok === false
    ? { tone: "red", text: "Wazuh not reachable" }
    : { tone: "blue", text: "Live · Wazuh connected" };
}
