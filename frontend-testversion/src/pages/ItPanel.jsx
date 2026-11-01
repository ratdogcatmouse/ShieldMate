// IT support panel: the clinic's IT contact sees open incidents, marks "Call received", leaves
// notes and marks it resolved with what was done. The owner then confirms the fix (or sends it
// back) on their own screen. The IT contact isn't a staff member, so the panel shows the
// owner's wording of each incident.
import { useEffect, useState } from "react";
import { Phone, Shield } from "../components/Icons.jsx";
import { Pill, StaleBanner, StatusPill, useAction, useToast } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { IT_PLAYBOOK, LOG_FIELD_LABEL, RULE_DESC } from "../lib/content.js";
import { deviceStates, fixNote, itAlertKeys, ownerOf, staffName } from "../lib/derive.js";
import { alertFx } from "../lib/fx.js";
import { seenOnce } from "../lib/session.js";
import { ago, fmtTime } from "../lib/time.js";
import { useBodyClass } from "../lib/useBodyClass.js";
import { usePoll } from "../lib/usePoll.js";

const STATUS = {
  none: ["grey", "Open · nobody has called yet"],
  called: ["red", "Incoming call"],
  received: ["amber", "You're on it"],
  resolved: ["blue", "Waiting for the owner to confirm"],
  closed: ["green", "Closed"],
};
const ORDER = { called: 0, received: 1, none: 2, resolved: 3 };
const RESOLVED_NOTE_MIN = 5;   // the server's rule, checked before sending

export default function ItPanel() {
  useBodyClass("it-body");
  const [run, busy] = useAction();
  const toast = useToast();
  const [drafts, setDrafts] = useState({});    // typed notes, per incident
  const [showClosed, setShowClosed] = useState(false);
  const { data, stale, refresh } = usePoll(async () => {
    const [clinic, list, actions, devices, incidents] = await Promise.all([
      api.getClinic(),
      api.getAlerts("owner", { includeClosed: true }),
      api.listOrEmpty(api.getActions(), "actions"),
      api.listOrEmpty(api.getDevices(), "devices"),
      api.listOrEmpty(api.getRestoreIncidents(), "incidents"),
    ]);
    return { clinic, alerts: list.alerts, actions, devices, incidents };
  }, 2000);

  const all = data?.alerts ?? [];
  const open = all.filter((a) => !a.it.closed_at && a.status !== "mine")
    .sort((x, y) => ORDER[x.it.status] - ORDER[y.it.status] || y.first_seen.localeCompare(x.first_seen));
  const closed = all.filter((a) => a.it.closed_at);

  // The backup incident (v3): a "not safe" restore check opened it; IT resolves it with a
  // note. It shows above the alert tickets while open; a closed one disappears (like alerts).
  const incidents = data?.incidents ?? [];
  const openBackup = incidents.find((i) => !i.closed_at);

  // Every new (or reopened) alert, and every call, buzzes and chimes once per tab: the IT contact
  // is told about all of the clinic's alerts, not only the ones staff call about.
  const ringing = itAlertKeys(open).join(",");
  useEffect(() => {
    const fresh = ringing ? ringing.split(",").filter((key) => !seenOnce(key)) : [];
    if (fresh.length) alertFx();
  }, [ringing]);

  const send = (a, action) => {
    const note = (drafts[a.id] || "").trim();
    if (action === "resolved" && note.length < RESOLVED_NOTE_MIN) {
      toast("Say what you did, so the owner can check it");
      document.getElementById(`note-${a.id}`)?.focus();
      return;
    }
    run(`${action}-${a.id}`, async () => {
      await api.itAction(a.id, action, note);
      if (action !== "received") setDrafts((d) => ({ ...d, [a.id]: "" }));
      toast(action === "received" ? "The owner can see you're on it" : action === "note" ? "Note added" : "Sent to the owner to confirm");
      await refresh();
    });
  };

  // The backup incident is a separate record (not an alert ticket), so it has its own draft
  // and its own resolve call. The owner is pinged by the server; IT just says what they did.
  const backupDraft = drafts["backup"] || "";
  const setBackupDraft = (v) => setDrafts((d) => ({ ...d, backup: v }));
  const resolveBackup = () => {
    const note = backupDraft.trim();
    if (note.length < RESOLVED_NOTE_MIN) {
      toast("Say what you did, so the owner can check it");
      document.getElementById("note-backup")?.focus();
      return;
    }
    run("resolve-backup", async () => {
      await api.resolveRestoreIncident(note);
      setDrafts((d) => ({ ...d, backup: "" }));
      toast("The owner has been told to retest and close it");
      await refresh();
    });
  };

  const c = data?.clinic;
  return (
    <>
      <StaleBanner stale={stale} />
      <header className="it-top">
        <div className="row" style={{ gap: 10, flexWrap: "nowrap", minWidth: 0 }}>
          <Shield style={{ width: 28, height: 28, color: "#fff" }} />
          <div className="stack-sm" style={{ gap: 0 }}>
            <span className="app-name" style={{ color: "#fff" }}>ShieldMate · IT support</span>
            <span className="small" style={{ color: "var(--night-muted)" }}>{c ? `${c.clinic.it_contact_name} · IT contact for ${c.clinic.name}` : ""}</span>
          </div>
        </div>
        <span className="pill pill-sim">{open.length ? `${open.length} open` : "All quiet"}</span>
      </header>
      <main className="it-main" aria-live="polite">
        <div className="col">
          {!data ? <p className="muted">Loading…</p> : (
            <>
              {openBackup ? <BackupTicket b={openBackup} clinic={data.clinic} busy={!!busy}
                draft={backupDraft} setDraft={setBackupDraft} onResolve={resolveBackup} /> : null}
              {open.length ? open.map((a) => (
            <Ticket key={a.id} a={a} clinic={c} act={data.actions.find((x) => x.id === a.action?.id)} busy={busy}
              draft={drafts[a.id] || ""} setDraft={(v) => setDrafts((d) => ({ ...d, [a.id]: v }))}
              onSend={(action) => send(a, action)} />
          )) : (
            <section className="card">
              <span className="ok-icon"><Shield /></span>
              <h1>Nothing open at {c.clinic.name}</h1>
              <p className="ink-2">Every alert at the clinic appears here the moment it happens. Keep this page open.</p>
            </section>
          )}
          {closed.length ? (
            <section className="card tight">
              <button type="button" className="row-between" style={{ background: "none", border: 0, padding: 0, font: "inherit", cursor: "pointer", width: "100%" }}
                aria-expanded={showClosed} onClick={() => setShowClosed(!showClosed)}>
                <span className="section-label" style={{ margin: 0 }}>Closed today ({closed.length})</span><span>{showClosed ? "▴" : "▾"}</span>
              </button>
              {showClosed ? closed.map((a) => (
                <div key={a.id} className="list-row" style={{ alignItems: "flex-start", flexDirection: "column", gap: 2 }}>
                  <span className="bold">{a.card.headline}</span>
                  <span className="small muted">Your fix: {fixNote(a)} · confirmed by {staffName(c, a.it.closed_by)} at {fmtTime(a.it.closed_at)}</span>
                </div>
              )) : null}
            </section>
          ) : null}
            </>
          )}
        </div>
        {c ? (
          <aside className="col">
            <section className="card tight">
              <span className="section-label">Clinic</span>
              <span className="bold" style={{ fontSize: 18 }}>{c.clinic.name}</span>
              <span className="small">Owner: {ownerOf(c)?.name} · signed in as {c.clinic.it_contact_name}</span>
            </section>
            <section className="list" aria-label="Computers">
              <h2 style={{ fontSize: 18, margin: "12px 0 4px" }}>Computers</h2>
              {deviceStates(c, data.devices.length ? data.devices : null, all.filter((a) => !a.it.closed_at)).map((d) => (
                <div key={d.agent} className="list-row">
                  <span>{d.short} <span className="small muted mono">{d.agent}</span></span>
                  <StatusPill status={d.status} />
                </div>
              ))}
            </section>
            <section className="card tight">
              <span className="section-label">How this works</span>
              <ol className="playbook small">
                <li>Staff call you and tick it on their phone.</li>
                <li>Tap <strong>Call received</strong> so the owner knows you're on it.</li>
                <li>When it's fixed, <strong>Mark resolved</strong> and say what you did.</li>
                <li>The owner confirms, or sends it back.</li>
              </ol>
            </section>
          </aside>
        ) : null}
      </main>
    </>
  );
}

function blockLine(act) {
  if (!act) return "No block proposed";
  const how = act.simulated ? " (simulated)" : " (sent through Wazuh)";
  if (act.status === "executed") return `Blocked until ${fmtTime(act.expires_at)}${how}`;
  if (act.status === "proposed") return "Waiting for the owner to approve";
  if (act.status === "failed") return "Block didn't take effect: Wazuh didn't answer";
  if (act.status === "refused") return `Not blocked: ${act.refused_reason || "protected address"}`;
  return `Block ${act.status}`;
}

// Backup incident ticket (v3): the IT contact sees the "not safe" restore check, reads the
// suggested fixes, and marks it resolved by saying what they did. The owner then retests.
function BackupTicket({ b, clinic, busy, draft, setDraft, onResolve }) {
  const isResolved = b.status === "resolved";
  const tone = isResolved ? "blue" : "red";
  const label = isResolved ? "Waiting for the owner to confirm" : "Not safe";
  return (
    <article className={`card ticket ${isResolved ? "resolved" : "open"} slide-in`} aria-label="Backup restore check not safe">
      <div className="row-between">
        <Pill tone={tone}>{label}</Pill>
        <span className="small muted">Opened {fmtTime(b.created_at)}</span>
      </div>
      <h2 style={{ fontSize: 20 }}>Backup restore check is not safe</h2>
      {!isResolved ? (
        <div className="callout amber">
          <span>The backup wouldn't restore cleanly. Fix it, then mark resolved so the owner can retest.</span>
        </div>
      ) : null}
      {b.fix_steps.length ? (
        <details className="log" open>
          <summary>Suggested fixes</summary>
          <div className="body">
            <ol className="playbook">{b.fix_steps.map((s) => <li key={s}>{s}</li>)}</ol>
          </div>
        </details>
      ) : null}
      {isResolved ? (
        <div className="callout blue">
          <span>You marked it resolved{b.it_resolved_at ? ` at ${fmtTime(b.it_resolved_at)}` : ""}. The owner is checking the backup now.</span>
        </div>
      ) : null}
      {!isResolved ? (
        <section className="stack-sm">
          <label className="field-label" htmlFor="note-backup">Note for the owner</label>
          <textarea
            className="it-note"
            id="note-backup"
            maxLength={300}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="What you checked or changed. To mark it resolved, say what you fixed."
          />
          <button type="button" className="btn btn-primary" disabled={!!busy} onClick={onResolve}>
            Mark resolved
          </button>
        </section>
      ) : null}
    </article>
  );
}

function Ticket({ a, clinic, act, busy, draft, setDraft, onSend }) {
  const it = a.it;
  const sentBack = it.status === "received" && it.sent_back_at;
  const [tone, label] = sentBack ? ["red", "Sent back by the owner"] : STATUS[it.status];
  const doneSteps = a.card.steps.filter((s) => s.done);
  const rows = [
    ["Wazuh rule", `${a.rule_id}${RULE_DESC[a.rule_id] ? ` · ${RULE_DESC[a.rule_id]}` : ""}`],
    ["Severity level", `${a.level} of 15`],
    ["Computer", <span className="mono">{a.agent_name}</span>],
    ["First seen", `${fmtTime(a.first_seen)} · last ${fmtTime(a.last_seen)}`],
    ["Count", `${a.count} event${a.count === 1 ? "" : "s"} grouped`],
    ["Source", a.source === "wazuh" ? "Live Wazuh feed" : "Recorded alert (replay)"],
    ["Playbook", <span className="mono">{a.lesson_id}</span>],
    // Log text is shown exactly, as text: never run, never followed.
    ...Object.entries(a.card.log_fields).map(([k, v]) => [LOG_FIELD_LABEL[k] || k, <span className="mono">{v}</span>]),
    ...(a.action ? [["Block", blockLine(act)]] : []),
    ["Done at the clinic", doneSteps.length ? doneSteps.map((s) => (
      <span key={s.action} style={{ display: "block" }}>{s.text} <span className="muted">({staffName(clinic, s.done_by)}, {fmtTime(s.done_at)})</span></span>
    )) : <span className="muted">Nothing yet</span>],
  ];
  const playbook = IT_PLAYBOOK[a.lesson_id] || [];
  return (
    <article className={`card ticket ${sentBack ? "sentback" : it.status}${it.status === "called" ? " slide-in" : ""}`} aria-label={a.card.headline}>
      <div className="row-between">
        <Pill tone={tone}>{label}</Pill>
        <span className="small muted">Started {fmtTime(a.first_seen)} · {ago(a.first_seen)}</span>
      </div>
      <h2 style={{ fontSize: 22 }}>{a.card.headline}</h2>
      {it.status === "called" ? (
        <div className="callout">
          <span><Phone /> {staffName(clinic, it.called_by)} called you at {fmtTime(it.called_at)} · {ago(it.called_at)}</span>
          <button type="button" className="btn btn-primary" disabled={!!busy} onClick={() => onSend("received")}>Call received</button>
        </div>
      ) : it.status === "none" ? (
        <div className="callout amber">
          <span>Nobody at the clinic has called yet. You can see it because you're their IT contact.</span>
          <button type="button" className="btn btn-soft" disabled={!!busy} onClick={() => onSend("received")}>I'm on it</button>
        </div>
      ) : sentBack ? (
        <div className="callout"><span>The owner checked and sent it back at {fmtTime(it.sent_back_at)}: “{it.sent_back_note}”</span></div>
      ) : it.status === "resolved" ? (
        <div className="callout blue"><span>You marked it resolved at {fmtTime(it.resolved_at)}. The owner is checking: “{it.resolved_note}”</span></div>
      ) : null}
      <details className="log" open>
        <summary>Technical details</summary>
        <div className="body">
          <dl className="kv">
            {rows.map(([k, v]) => [<dt key={`${k}-t`}>{k}</dt>, <dd key={`${k}-d`}>{v}</dd>])}
          </dl>
        </div>
      </details>
      {playbook.length ? (
        <details className="log">
          <summary>Suggested fix</summary>
          <div className="body"><ol className="playbook">{playbook.map((x) => <li key={x}>{x}</li>)}</ol></div>
        </details>
      ) : null}
      {it.status === "received" ? (
        <section className="stack-sm">
          <label className="field-label" htmlFor={`note-${a.id}`}>Note for the owner</label>
          <textarea className="it-note" id={`note-${a.id}`} maxLength={300} value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="What you checked or changed. To mark it resolved, say what fixed it." />
          <div className="row">
            <button type="button" className="btn btn-primary" disabled={!!busy} onClick={() => onSend("resolved")}>Mark resolved</button>
            <button type="button" className="btn btn-soft" disabled={!!busy || !draft.trim()} onClick={() => onSend("note")}>Add note only</button>
          </div>
        </section>
      ) : null}
      {it.log.length ? (
        <section className="stack-sm">
          <span className="section-label">History</span>
          <div className="timeline">
            {[...it.log].reverse().map((l, i) => (
              <div key={i} className="ev">
                <time>{fmtTime(l.at)}</time>
                <span><strong>{l.by_staff_id === null ? clinic.clinic.it_contact_name : staffName(clinic, l.by_staff_id)}:</strong> {LOG_TEXT[l.kind](l, clinic)}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </article>
  );
}

// One history line per kind; notes are people's own words, shown as text.
const LOG_TEXT = {
  called: (_, c) => `Called ${c.clinic.it_contact_name}`,
  received: () => "Picked it up",
  note: (l) => l.note,
  resolved: (l) => `Marked resolved: ${l.note}`,
  confirmed: () => "Confirmed it's fixed. Closed",
  sent_back: (l) => `Sent back: ${l.note}`,
};
