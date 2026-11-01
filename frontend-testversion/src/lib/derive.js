// Facts the screens work out from API data, shared so the owner page, the IT panel and
// mission control always agree.
import { ACTION_LABEL, CERTIN_HOURS, DEVICE_STATUS, SCENARIOS, deviceShort } from "./content.js";
import { toMs } from "./time.js";

export const ownerOf = (clinic) => clinic.staff.find((s) => s.role === "owner") || null;
export const staffName = (clinic, id) => clinic.staff.find((s) => s.id === id)?.name ?? "Someone";

const isOpen = (a) => !a.it.closed_at;
export const passwordAlert = (alerts) => alerts.find((a) => a.lesson_id === "password_guessing" && isOpen(a)) || null;
export const ransomwareAlert = (alerts) =>
  alerts.find((a) => a.lesson_id === "ransomware" && isOpen(a) && a.status !== "mine") || null;

// The operations view's people panel: how far one staff member is with an alert, read from their own
// role's list (GET /alerts?role=<theirs>). null when it isn't theirs: the alert is on somebody
// else's computer, so it never reached their phone.
export function stepProgress(alertsByRole, role, alertId) {
  const a = (alertsByRole[role] || []).find((x) => x.id === alertId);
  if (!a) return null;
  return { done: a.card.steps.filter((s) => s.done).length, total: a.card.steps.length };
}

// The IT panel's chimes: one key per open alert as it arrives (and again when it reopens), plus
// one per incoming call. The panel chimes once per key per tab, so the IT contact hears about
// every alert, not only the ones staff call about. Times are in the keys because alert ids
// start again from 1 after a Reset.
export function itAlertKeys(open) {
  return open.flatMap((a) => [
    `it-new-${a.id}-${a.first_seen}${a.reopened ? `-r-${a.mine_at}` : ""}`,
    ...(a.it.status === "called" ? [`it-call-${a.id}-${a.it.called_at}`] : []),
  ]);
}

// Every other open incident (phishing, the three v4 drills' attacks, ...): the owner page and
// mission control show these generically, since they have no screen of their own.
const NAMED = ["password_guessing", "ransomware"];
export const otherAlerts = (alerts) =>
  alerts.filter((a) => isOpen(a) && a.status !== "mine" && !NAMED.includes(a.lesson_id));

// v4: the attack simulation's outcome (GET /status `simulation`) in words the team understands.
// null while nothing has run, while it's still running (the cards tell that story), or after Reset.
export function simResult(sim, clinic) {
  if (!sim || sim.status === "running") return null;
  const clock = (ms) => {
    const s = Math.max(0, Math.round(ms / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };
  const label = (id) => ACTION_LABEL[id] || id;
  if (sim.status === "contained") {
    const by = sim.contained_by;
    const who = !by ? "The team" : by.staff_id === null ? "The standing rule" : staffName(clinic, by.staff_id);
    const later = sim.phases_cancelled === 1 ? "The next stage never happened." : `${sim.phases_cancelled} later stages never happened.`;
    return {
      tone: "green",
      title: by ? `Attack stopped in ${clock(toMs(by.at) - toMs(sim.started_at))}` : "Attack stopped",
      line: `${who}: ${by ? label(by.action).toLowerCase() : "acted in time"}. ${later}`,
      what: sim.title,
    };
  }
  if (sim.status === "spread") {
    return {
      tone: "red",
      title: "The attack got through",
      line: `What would have stopped it: ${sim.stop_actions.map((a) => label(a).toLowerCase()).join(", or ")}.`,
      what: sim.title,
    };
  }
  return {
    tone: "grey",
    title: "Practice attack ended early",
    line: sim.status === "stopped" ? "It was stopped from Backstage before the end." : "It ran out of time before the end.",
    what: sim.title,
  };
}

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

// Signal vs noise, from the alert list the API already returns (`hidden_count` + `alerts`, the
// owner's view with closed incidents included) and the block requests:
//   events    every Wazuh event ShieldMate looked at (hidden routine ones + each card's grouped count)
//   hidden    routine events filtered out (level too low, or no lesson)
//   incidents cards raised for people (one per rule + computer group)
//   steps     ticked checklist steps across those cards (the owner's view), out of all of them
//   blocks    block requests that were carried out
export function signalStats(list, actions = []) {
  const alerts = list?.alerts ?? [];
  const hidden = list?.hidden_count ?? 0;
  const grouped = alerts.reduce((n, a) => n + a.count, 0);
  const steps = alerts.flatMap((a) => a.card.steps);
  return {
    events: hidden + grouped,
    hidden,
    grouped,
    incidents: alerts.length,
    stepsDone: steps.filter((s) => s.done).length,
    stepsTotal: steps.length,
    blocks: actions.filter((x) => ["executed", "expired", "undone"].includes(x.status)).length,
  };
}

// System health rows for the owner's sidebar: where alerts come from and whether Wazuh answers.
// Each row is [label, value, state] with state "ok", "bad" or "off" (not used in replay mode).
export function healthRows(status) {
  if (!status) return [];
  const live = status.alert_source === "wazuh";
  const yes = (v) => (v === false ? ["Not reachable", "bad"] : v === true ? ["Connected", "ok"] : ["Unknown", "off"]);
  return [
    ["Alert source", live ? "Live Wazuh feed" : "Recorded alerts", live ? "ok" : "off"],
    ["Wazuh API", ...(live ? yes(status.wazuh.api_ok) : ["Not used in replay", "off"])],
    ["Indexer", ...(live ? yes(status.wazuh.indexer_ok) : ["Not used in replay", "off"])],
  ];
}
