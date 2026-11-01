import { describe, expect, it } from "vitest";
import {
  activity, certinDue, deviceStates, drillFor, healthRows, itAlertKeys, otherAlerts, passwordAlert, ransomwareAlert, restoreSince,
  signalStats, simResult, stepProgress,
} from "./derive.js";
import { fmtTime, left, mmss, stopwatch } from "./time.js";

const clinic = {
  clinic: { it_contact_name: "Suresh", approval_timeout_minutes: 5 },
  staff: [{ id: 1, name: "Meena", role: "front_desk" }, { id: 3, name: "Dr. Rao", role: "owner" }],
  devices: [
    { agent_name: "RECEPTION-PC", location: "Front desk" },
    { agent_name: "FILE-SERVER", location: "Back office" },
  ],
};
const IT_NONE = { status: "none", closed_at: null, log: [] };

function alert(over) {
  return {
    id: 1, lesson_id: "password_guessing", agent_name: "RECEPTION-PC", status: "new",
    first_seen: "2026-11-01T04:00:00Z", mine_at: null, mine_by: null,
    card: { headline: "Someone is guessing.", steps: [], drill_scenario: null },
    it: IT_NONE, ...over,
  };
}

describe("deviceStates", () => {
  it("marks the PC under attack from an open password alert when ACTIONS is off", () => {
    const d = deviceStates(clinic, null, [alert()]);
    expect(d.map((x) => [x.agent, x.status])).toEqual([["RECEPTION-PC", "under_attack"], ["FILE-SERVER", "ok"]]);
    expect(d[0]).toMatchObject({ short: "Reception", label: "Under attack", tone: "red" });
  });

  it("uses the server's strip when it has one", () => {
    const api = [{ agent_name: "RECEPTION-PC", status: "protected", block: { target_ip: "1.2.3.4" } }];
    expect(deviceStates(clinic, api, [alert()])[0]).toMatchObject({ status: "protected", block: { target_ip: "1.2.3.4" } });
  });

  it("shows ransomware as files locked, then cut off once isolated", () => {
    const rw = alert({ id: 2, lesson_id: "ransomware", agent_name: "FILE-SERVER", card: { headline: "x", steps: [] } });
    expect(deviceStates(clinic, null, [rw])[1].status).toBe("files_locked");
    rw.card.steps = [{ action: "ISOLATE_NETWORK", done: true }];
    expect(deviceStates(clinic, null, [rw])[1].status).toBe("isolated");
  });
});

describe("alert picks", () => {
  it("skips closed incidents and paused ransomware", () => {
    const closed = alert({ it: { ...IT_NONE, closed_at: "2026-11-01T05:00:00Z" } });
    expect(passwordAlert([closed])).toBeNull();
    expect(ransomwareAlert([alert({ lesson_id: "ransomware", status: "mine" })])).toBeNull();
  });

  it("gives ransomware a CERT-In deadline six hours on, and password guessing none", () => {
    expect(certinDue(alert({ lesson_id: "ransomware" }))).toBe(Date.parse("2026-11-01T10:00:00Z"));
    expect(certinDue(alert())).toBeNull();
  });

  it("finds the drill for an alert: the lesson's own, else a scenario named after it", () => {
    expect(drillFor(alert())).toBe("password_guessing");
    expect(drillFor(alert({ lesson_id: "phishing_flagged" }))).toBeNull();
    expect(drillFor(alert({ card: { drill_scenario: "ransomware_clinic", steps: [] } }))).toBe("ransomware_clinic");
  });

  it("counts a restore check only if it ran after the alert started", () => {
    const run = { result: "FAIL", started_at: "2026-11-01T03:59:00Z" };
    expect(restoreSince(run, alert())).toBeNull();
    expect(restoreSince({ ...run, started_at: "2026-11-01T04:01:00Z" }, alert())).not.toBeNull();
    expect(restoreSince({ result: "NOT_TESTED", started_at: null }, alert())).toBeNull();
  });
});

describe("activity", () => {
  it("builds a newest-first timeline from alerts, steps, the IT log, actions and notifications", () => {
    const a = alert({
      card: { headline: "Someone is guessing.", steps: [{ action: "DONT_USE_DEVICE", text: "Don't log in.", done: true, done_by: 1, done_at: "2026-11-01T04:02:00Z" }] },
      it: { ...IT_NONE, log: [{ at: "2026-11-01T04:03:00Z", kind: "called", by_staff_id: 1, note: null },
        { at: "2026-11-01T04:04:00Z", kind: "received", by_staff_id: null, note: null }] },
    });
    const actions = [{ status: "executed", target_ip: "192.168.1.57", proposed_at: "2026-11-01T04:00:30Z",
      decided_at: "2026-11-01T04:05:00Z", decided_via: "standing_rule" }];
    const notes = [{ created_at: "2026-11-01T04:06:00Z", text: "Meena handled it" }];
    expect(activity(clinic, [a], actions, notes).map((e) => e.text)).toEqual([
      "Meena handled it",
      "Blocked 192.168.1.57 under the standing rule",
      "Suresh picked it up",
      "Meena called Suresh",
      "Meena: Don't log in",
      "ShieldMate asked to block 192.168.1.57",
      "Someone is guessing",
    ]);
  });
});

describe("activity: live Wazuh alerts and attack notes", () => {
  const live = (over) => alert({
    source: "wazuh", rule_id: "60204", count: 8,
    card: { headline: "Someone is repeatedly guessing the password on RECEPTION-PC.", steps: [], log_fields: { source_ip: "192.168.137.50" } },
    ...over,
  });

  it("drops attack notes (the alert's own line already says it) but keeps plain ones", () => {
    const notes = [
      { kind: "attack", created_at: "2026-11-01T04:01:00Z", text: "Someone is repeatedly guessing the password on RECEPTION-PC." },
      { kind: "info", created_at: "2026-11-01T04:02:00Z", text: "Meena handled it" },
    ];
    expect(activity(clinic, [alert()], [], notes).map((e) => e.text)).toEqual(["Meena handled it", "Someone is guessing"]);
  });

  it("tags a wazuh alert as live and gives its rule id and the attacker's address", () => {
    const [line] = activity(clinic, [live()], [], []);
    expect(line.tag).toBe("LIVE · Wazuh");
    expect(line.text).toBe("rule 60204 — Password guessing on RECEPTION-PC from 192.168.137.50 ×8");
  });

  it("takes the address from the block request when the card doesn't show it", () => {
    const a = live({ card: { headline: "x", steps: [], log_fields: {} } });
    const [line] = activity(clinic, [a], [{ alert_id: 1, status: "proposed", target_ip: "192.168.137.50", proposed_at: "2026-11-01T03:00:00Z" }], []);
    expect(line.text).toContain("from 192.168.137.50");
  });

  it("leaves out the address when there is none (ransomware) and the count when it is 1", () => {
    const a = live({ lesson_id: "ransomware", rule_id: "100201", agent_name: "FILE-SERVER", count: 1,
      card: { headline: "x", steps: [], log_fields: {} } });
    expect(activity(clinic, [a], [], [])[0].text).toBe("rule 100201 — Ransomware on FILE-SERVER");
  });

  it("is one line per alert however high the count goes", () => {
    const lines = activity(clinic, [live({ count: 9 })], [], []).filter((e) => e.tag);
    expect(lines).toHaveLength(1);
    expect(lines[0].text.endsWith("×9")).toBe(true);
  });

  it("keeps a replayed alert's wording and gives it no tag", () => {
    const [line] = activity(clinic, [alert({ source: "replay" })], [], []);
    expect(line).toMatchObject({ text: "Someone is guessing" });
    expect(line.tag).toBeUndefined();
  });
});

describe("time formatting", () => {
  it("shows Indian time from UTC", () => {
    expect(fmtTime("2026-11-01T04:10:00Z")).toBe("9:40 AM");
    expect(fmtTime(null)).toBe("");
  });

  it("formats countdowns and stopwatches", () => {
    expect(mmss(245)).toBe("4:05");
    expect(mmss(-3)).toBe("0:00");
    expect(stopwatch(65)).toBe("01:05");
    expect(left(Date.parse("2026-11-01T10:00:00Z"), Date.parse("2026-11-01T04:22:00Z"))).toBe("5 h 38 min left");
  });
});

// v4: the attack simulation's outcome, as the team's screens word it.
describe("simResult", () => {
  const sim = (over) => ({
    script_id: "supplier_bank_fraud", title: "A fake supplier asks for payment to a new bank account",
    status: "contained", started_at: "2026-11-01T04:00:00Z", finished_at: "2026-11-01T04:02:00Z",
    elapsed_ms: 120000, phases_fired: 1, phases_cancelled: 1, stop_actions: ["VERIFY_BY_CALLBACK"],
    contained_by: { action: "VERIFY_BY_CALLBACK", staff_id: 1, at: "2026-11-01T04:01:05Z" }, ...over,
  });

  it("is null before anything ran and while it runs", () => {
    expect(simResult(null, clinic)).toBeNull();
    expect(simResult(sim({ status: "running", contained_by: null }), clinic)).toBeNull();
  });

  it("names who stopped it, with what, and how fast", () => {
    const r = simResult(sim(), clinic);
    expect(r).toMatchObject({ tone: "green", title: "Attack stopped in 1:05" });
    expect(r.line).toBe("Meena: check by calling back on a number you already have. The next stage never happened.");
  });

  it("credits the standing rule when nobody tapped", () => {
    const r = simResult(sim({ phases_cancelled: 2, contained_by: { action: "BLOCK_IP", staff_id: null, at: "2026-11-01T04:05:00Z" } }), clinic);
    expect(r.line).toBe("The standing rule: block the attacking address. 2 later stages never happened.");
  });

  it("says what would have stopped a spread attack", () => {
    const r = simResult(sim({ status: "spread", contained_by: null, stop_actions: ["BLOCK_IP", "ISOLATE_NETWORK"] }), clinic);
    expect(r.tone).toBe("red");
    expect(r.line).toBe("What would have stopped it: block the attacking address, or unplug the network, leave the computer on.");
  });

  it("calls a Backstage stop an early end", () => {
    expect(simResult(sim({ status: "stopped", contained_by: null }), clinic)).toMatchObject({ tone: "grey", title: "Practice attack ended early" });
  });
});

describe("otherAlerts", () => {
  it("keeps open incidents that have no screen of their own", () => {
    const list = [
      alert({ id: 1 }),
      alert({ id: 2, lesson_id: "ransomware" }),
      alert({ id: 3, lesson_id: "supplier_bank_change" }),
      alert({ id: 4, lesson_id: "phishing_flagged", it: { ...IT_NONE, closed_at: "2026-11-01T05:00:00Z" } }),
    ];
    expect(otherAlerts(list).map((a) => a.id)).toEqual([3]);
  });
});

describe("stepProgress", () => {
  const steps = [{ action: "DONT_USE_DEVICE", done: true }, { action: "CALL_SAVED_IT", done: false }];
  const byRole = { front_desk: [alert({ id: 7, card: { headline: "x", steps } })], billing: [] };

  it("reads a person's progress from their own role's card", () => {
    expect(stepProgress(byRole, "front_desk", 7)).toEqual({ done: 1, total: 2 });
  });

  it("is null for someone the alert never reached (another person's computer)", () => {
    expect(stepProgress(byRole, "billing", 7)).toBeNull();
    expect(stepProgress(byRole, "front_desk", 8)).toBeNull();
    expect(stepProgress({}, "billing", 7)).toBeNull();
  });
});

describe("itAlertKeys", () => {
  it("gives every open alert a key, so the IT panel chimes before anyone calls", () => {
    expect(itAlertKeys([alert({ id: 1 }), alert({ id: 2, first_seen: "2026-11-01T05:00:00Z" })])).toEqual([
      "it-new-1-2026-11-01T04:00:00Z", "it-new-2-2026-11-01T05:00:00Z",
    ]);
  });

  it("adds a key for an incoming call, and a fresh one when the alert reopens", () => {
    const called = alert({ it: { ...IT_NONE, status: "called", called_at: "2026-11-01T04:01:00Z" } });
    expect(itAlertKeys([called])).toEqual(["it-new-1-2026-11-01T04:00:00Z", "it-call-1-2026-11-01T04:01:00Z"]);
    const reopened = alert({ reopened: true, mine_at: "2026-11-01T04:02:00Z" });
    expect(itAlertKeys([reopened])).toEqual(["it-new-1-2026-11-01T04:00:00Z-r-2026-11-01T04:02:00Z"]);
  });

  it("never repeats a key after a Reset restarts the ids, because the time differs", () => {
    const before = itAlertKeys([alert({ id: 1 })]);
    const after = itAlertKeys([alert({ id: 1, first_seen: "2026-11-01T06:00:00Z" })]);
    expect(after).not.toEqual(before);
  });

  it("is empty when nothing is open", () => {
    expect(itAlertKeys([])).toEqual([]);
  });
});

describe("signalStats", () => {
  const card = (done) => ({ steps: done.map((d) => ({ done: d })) });
  it("adds the hidden routine events to each card's grouped count", () => {
    const list = { hidden_count: 40, alerts: [{ count: 8, card: card([true, false]) }, { count: 3, card: card([true]) }] };
    const actions = [{ status: "executed" }, { status: "declined" }, { status: "expired" }];
    expect(signalStats(list, actions)).toEqual({
      events: 51, hidden: 40, grouped: 11, incidents: 2, stepsDone: 2, stepsTotal: 3, blocks: 2,
    });
  });
  it("is all zeros before the first poll", () => {
    expect(signalStats(null)).toEqual({ events: 0, hidden: 0, grouped: 0, incidents: 0, stepsDone: 0, stepsTotal: 0, blocks: 0 });
  });
});

describe("healthRows", () => {
  it("marks Wazuh as not used in replay mode", () => {
    const rows = healthRows({ alert_source: "replay", wazuh: { api_ok: null, indexer_ok: null } });
    expect(rows.map((r) => r[2])).toEqual(["off", "off", "off"]);
  });
  it("shows a live feed whose indexer is down", () => {
    const rows = healthRows({ alert_source: "wazuh", wazuh: { api_ok: true, indexer_ok: false } });
    expect(rows).toEqual([
      ["Alert source", "Live Wazuh feed", "ok"], ["Wazuh API", "Connected", "ok"], ["Indexer", "Not reachable", "bad"],
    ]);
  });
  it("has no rows before the first poll", () => {
    expect(healthRows(null)).toEqual([]);
  });
});
