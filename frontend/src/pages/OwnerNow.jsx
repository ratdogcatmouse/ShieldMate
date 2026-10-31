// Owner: Right now. Live approval card, ransomware incident, IT support, computers, activity.
// Laptop: side menu. Phone (under 900 px): bottom tabs.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Clock, Phone, Shield } from "../components/Icons.jsx";
import { Rephrasable, RephraseProvider } from "../components/Rephrase.jsx";
import { OwnerShell } from "../components/Shells.jsx";
import { Countdown, FeedTag, Pill, SimResult, StatusPill, TimeLeft, useAction, useToast } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { alertFx } from "../lib/fx.js";
import {
  activity, certinDue, decideBy, deviceStates, drillFor, fixNote, otherAlerts, ownerOf, passwordAlert, ransomwareAlert,
  restoreSince, simResult, sourceBadge, staffName,
} from "../lib/derive.js";
import { deviceName } from "../lib/content.js";
import { seenOnce } from "../lib/session.js";
import { ago, fmtTime, serverNow, toMs } from "../lib/time.js";
import { usePoll } from "../lib/usePoll.js";

async function load() {
  const [clinic, status, list, actions, devices, restore, notes] = await Promise.all([
    api.getClinic(),
    api.getStatus(),
    api.getAlerts("owner", { includeClosed: true }),
    api.listOrEmpty(api.getActions(), "actions"),
    api.listOrEmpty(api.getDevices(), "devices"),
    api.getRestoreLatest(),
    api.getNotifications("owner"),
  ]);
  return { clinic, status, list, actions, devices, restore, notes: notes.notifications };
}

export default function OwnerNow() {
  const { data, stale, refresh } = usePoll(load, 2000);
  const [run, busy] = useAction();
  const toast = useToast();
  const [sendBack, setSendBack] = useState({ id: null, text: "" });

  const pw = data ? passwordAlert(data.list.alerts) : null;
  const act = pw?.action ? data.actions.find((x) => x.id === pw.action.id) : null;

  // A block request that just arrived slides in once, and the phone buzzes once.
  const freshKey = act && act.status === "proposed" ? `owner-act-${act.id}` : null;
  const [fresh, setFresh] = useState(null);
  useEffect(() => {
    if (freshKey && !seenOnce(freshKey)) {
      setFresh(freshKey);
      alertFx();
    }
  }, [freshKey]);

  if (!data) return <OwnerShell stale={stale}><p className="muted">Loading…</p></OwnerShell>;

  const { clinic, actions, restore } = data;
  const owner = ownerOf(clinic);
  const alerts = data.list.alerts.filter((a) => !a.it.closed_at);
  const closed = data.list.alerts.filter((a) => a.it.closed_at);
  const rw = ransomwareAlert(alerts);
  const devices = deviceStates(clinic, data.devices.length ? data.devices : null, alerts);
  const badge = sourceBadge(data.status);
  const doAct = (key, fn, message) => run(key, async () => { await fn(); if (message) toast(message); await refresh(); });

  // Order: decisions needed first, then the ransomware incident, then things already handled.
  const first = [];
  const main = [];
  let urgent = false;
  if (pw?.status === "mine") {
    main.push(<MineCard key="mine" a={pw} clinic={clinic} />);
  } else if (act?.status === "proposed") {
    first.push(<ApprovalCard key="approve" act={act} alert={pw} clinic={clinic} fresh={fresh === freshKey} busy={busy}
      onApprove={() => doAct("approve", () => api.approve(act.id, owner.id))}
      onDecline={() => doAct("decline", () => api.decline(act.id, owner.id))} />);
    urgent = true;
  } else if (act?.status === "executed") {
    main.push(<BlockedCard key="blocked" act={act} clinic={clinic} ownerId={owner.id} busy={busy}
      onUndo={() => doAct("undo", () => api.undo(act.id, owner.id))} />);
  } else if (act && ["declined", "failed", "refused"].includes(act.status)) {
    first.push(<NotBlockedCard key="notblocked" act={act} clinic={clinic} />);
    urgent = true;
  } else if (pw?.status === "new") {
    first.push(<NeedsYou key="pw" a={pw} />);
    urgent = true;
  }
  if (rw) {
    main.push(<IncidentHead key="rw-head" a={rw} />);
    main.push(<CertIn key="rw-certin-phone" a={rw} className="phone-only" />);
    main.push(<Checklist key="rw-checklist" a={rw} restore={restore} busy={busy}
      onTick={(s) => doAct(`tick-${s.action}`, () => api.setStep(rw.id, s.action, owner.id, !s.done))}
      onRestore={() => doAct("restore", async () => {
        await new Promise((r) => setTimeout(r, 1500));      // the check is quick; give the moment some weight
        await api.runRestore();
        await api.setStep(rw.id, "VERIFY_BACKUP", owner.id, true);
      })} />);
    urgent = true;
  }
  // Every other incident (phishing, the remote-control and supplier-fraud attacks, ...): the
  // card's own headline and a tickable checklist, so a tick here counts like one on a phone.
  const others = otherAlerts(alerts);
  for (const a of others) {
    main.push(<IncidentHead key={`head-${a.id}`} a={a} />);
    main.push(<Checklist key={`list-${a.id}`} a={a} restore={restore} busy={busy}
      onTick={(s) => doAct(`tick-${a.id}-${s.action}`, () => api.setStep(a.id, s.action, owner.id, !s.done))}
      onRestore={() => {}} />);
    if (a.severity === "needs_you_now" && a.status === "new") urgent = true;
  }
  for (const a of [rw, pw && pw.status !== "mine" ? pw : null, ...others].filter(Boolean)) {
    main.push(<ItCard key={`it-${a.id}`} a={a} clinic={clinic} busy={busy} sendBack={sendBack} setSendBack={setSendBack}
      onConfirm={() => doAct(`confirm-${a.id}`, () => api.closeIncident(a.id, owner.id, true), "Incident closed")}
      onSendBack={() => doAct(`sendback-${a.id}`, async () => {
        await api.closeIncident(a.id, owner.id, false, sendBack.text.trim());
        setSendBack({ id: null, text: "" });
      }, "Sent back to IT")} />);
    // IT says it's fixed: that's a decision for the owner, so the nav shows it as needing attention.
    if (a.it.status === "resolved") urgent = true;
  }
  const handled = alerts.filter((a) => drillFor(a) && (a.status === "done" || (a === pw && ["executed", "expired", "undone"].includes(act?.status))));

  return (
    <RephraseProvider role="owner" lang="en">
    <OwnerShell clinicName={clinic.clinic.name} ownerName={owner?.name} urgent={urgent} stale={stale}>
      <div className="owner-head">
        <div><span className="owner-mobile-head">{clinic.clinic.name}</span><h1>Right now</h1></div>
        <Pill tone={badge.tone}>{badge.text}</Pill>
      </div>
      <div className="cols">
        <div className="col-main">
          <SimResult result={simResult(data.status.simulation, clinic)} />
          {first}
          {main}
          {!first.length && !main.length ? (
            <section className="card">
              <span className="ok-icon"><Shield /></span>
              <h1>All clear</h1>
              <p className="ink-2">
                Nothing needs you right now. ShieldMate is watching {clinic.devices.length} computers
                {data.list.hidden_count ? ` and has hidden ${data.list.hidden_count} routine events today` : ""}.
              </p>
              <span className="small muted">Use Backstage to replay an attack for the demo.</span>
            </section>
          ) : null}
          {handled.length ? (
            <section className="card tight">
              <span className="section-label">Practise what just happened</span>
              {handled.slice(0, 2).map((a) => (
                <div key={a.id} className="row-between">
                  <span>{a.card.headline.replace(/\.$/, "")}</span>
                  <Link className="btn btn-ghost" to={`/owner/drill?scenario=${drillFor(a)}&alert=${a.id}`}>Practise this with the team</Link>
                </div>
              ))}
            </section>
          ) : null}
          <ClosedToday closed={closed} clinic={clinic} />
        </div>
        <aside className="col-side">
          {rw ? <CertIn a={rw} className="laptop-only" /> : null}
          <section className="list" aria-label="Computers">
            <h2 style={{ fontSize: 18, margin: "12px 0 4px" }}>Computers</h2>
            {devices.map((d) => (
              <div key={d.agent} className="list-row"><span>{d.short}</span><StatusPill status={d.status} /></div>
            ))}
          </section>
          {data.devices.length ? ( /* GET /devices answers only with ACTIONS on, like the rule's route */
            <StandingRule clinic={clinic} busy={busy}
              onToggle={() => doAct("rule", () => api.setStandingRule(!clinic.clinic.standing_rule_block_ip, owner.id))} />
          ) : null}
          <Activity events={activity(clinic, data.list.alerts, actions, data.notes)} />
        </aside>
      </div>
    </OwnerShell>
    </RephraseProvider>
  );
}

function NeedsYou({ a }) {
  return (
    <Rephrasable id={`alert-${a.id}`} kind="Alert" title={a.card.headline} text={`${a.card.what_we_know} ${a.card.why}`} alertId={a.id}>
      <article className="card">
        <Pill tone="red">Needs you now</Pill>
        <h1>{a.card.headline}</h1>
        <p className="ink-2">{a.card.what_we_know}</p>
      </article>
    </Rephrasable>
  );
}

function ApprovalCard({ act, alert, clinic, fresh, busy, onApprove, onDecline }) {
  const rule = act.on_timeout === "block_under_standing_rule";
  const due = decideBy(act, clinic);
  const backup = clinic.staff.find((s) => s.is_backup_approver);
  const late = act.seconds_left === 0;
  const title = `Block the attacker on the ${deviceName(alert.agent_name).toLowerCase()} for ${clinic.clinic.block_minutes} minutes?`;
  return (
    <Rephrasable id={`action-${act.id}`} kind="Decision" alertId={alert.id} title={title}
      text={`${alert.count}+ wrong passwords. It stops only that address for ${clinic.clinic.block_minutes} minutes. ${rule ? "If you don't answer, your standing rule blocks it." : "If you don't answer in time, your backup person is asked."}`}>
    <article className={`card outlined${fresh ? " slide-in" : ""}`}>
      <Pill tone="red">{late ? "Still needs your decision" : "Your decision needed"}</Pill>
      <h1>{title}</h1>
      <p className="ink-2">
        {alert.count}+ wrong passwords from <span className="mono">{act.target_ip}</span>.
        {alert.status === "done" ? ` ${staffName(clinic, alert.done_by)} has already stopped using that computer.` : ""}
      </p>
      <div className="facts">
        <div className="fact"><span className="k">What it does</span><span className="v">Stops only that address</span></div>
        <div className="fact"><span className="k">How long</span><span className="v">{clinic.clinic.block_minutes} minutes</span></div>
        <div className="fact"><span className="k">If you don't answer</span><span className="v">{rule ? "Your rule blocks it" : "Backup person is asked"}</span></div>
      </div>
      <div className="tinted row nowrap" style={{ gap: 8 }}>
        <Clock />
        <span>
          {late && !rule ? <>Nobody answered in time, so we asked {backup ? backup.name : "your backup person"}. You can still decide.</>
            : rule ? <>Your rule blocks it at <strong>{fmtTime(due)}</strong> if you don't answer · <span className="mono bold"><Countdown to={due} /></span></>
            : <>If you don't answer by <strong>{fmtTime(due)}</strong>, we'll ask {backup ? backup.name : "your backup person"} · <span className="mono bold"><Countdown to={due} /></span></>}
        </span>
      </div>
      <div className="btn-group">
        <button type="button" className="btn btn-primary btn-lg" disabled={!!busy} onClick={onApprove}>Approve block</button>
        <button type="button" className="btn btn-soft btn-lg" disabled={!!busy} onClick={onDecline}>Decline</button>
      </div>
      <span className="small muted">Proposed by ShieldMate's fixed rules, not by AI.{act.simulated ? " In demo mode the block is simulated." : ""}</span>
    </article>
    </Rephrasable>
  );
}

function BlockedCard({ act, clinic, ownerId, busy, onUndo }) {
  // Staff can approve too (the Block button on their phone, or Ravi as the backup approver).
  const how = act.decided_via === "standing_rule" ? "by your standing rule"
    : act.decided_by === ownerId ? "by you" : `by ${staffName(clinic, act.decided_by)}`;
  return (
    <article className="card" role="status">
      <Pill tone="green">Blocked · approved {how} at {fmtTime(act.decided_at)}</Pill>
      <h1>The attacker can't reach the {deviceName(act.agent_name).toLowerCase()}.</h1>
      <p className="ink-2">The block on <span className="mono">{act.target_ip}</span> lifts by itself at {fmtTime(act.expires_at)}.</p>
      <div className="row">
        {act.undo_available ? <button type="button" className="btn btn-soft" disabled={!!busy} onClick={onUndo}>Undo block</button> : null}
        <span className="small ink-2">Next: ask your IT contact to change the password on that computer.</span>
      </div>
      {act.simulated ? <span className="pill pill-sim">Simulated action</span> : null}
    </article>
  );
}

// Declined, failed (Wazuh didn't answer) or refused (a protected address): nothing was blocked.
function NotBlockedCard({ act, clinic }) {
  const label = act.status === "declined" ? "Declined · no action taken"
    : act.status === "failed" ? "The block didn't take effect" : "ShieldMate won't block that address";
  return (
    <article className="card urgent" role="alert">
      <Pill tone={act.status === "declined" ? "grey" : "red"} noDot={act.status === "declined"}>{label}</Pill>
      <h1>The attack on the {deviceName(act.agent_name).toLowerCase()} may still be going.</h1>
      <p className="ink-2">
        {act.status === "refused" && act.refused_reason ? `${act.refused_reason}. ` : ""}
        Call your IT contact now, and keep staff off that computer.
      </p>
      <a className="btn btn-primary" style={{ alignSelf: "flex-start" }} href={`tel:${clinic.clinic.it_contact_phone}`}>
        <Phone /> Call {clinic.clinic.it_contact_name}
      </a>
    </article>
  );
}

function MineCard({ a, clinic }) {
  return (
    <article className="card tight">
      <Pill tone="blue" noDot>Paused · "That was me"</Pill>
      <span className="bold">{staffName(clinic, a.mine_by)} says the wrong passwords on the {deviceName(a.agent_name).toLowerCase()} were their own typing.</span>
      <span className="small muted">{fmtTime(a.mine_at)}. The alert comes back if it happens again within an hour.</span>
    </article>
  );
}

function IncidentHead({ a }) {
  return (
    <Rephrasable id={`alert-${a.id}`} kind="Alert" title={a.card.headline} text={`${a.card.what_we_know} ${a.card.why}`} alertId={a.id}>
      <article className="card">
        <div className="row">
          {a.severity === "heads_up" ? <Pill tone="amber">Heads up</Pill> : <Pill tone="red">Needs you now</Pill>}
          <span className="small muted">Started {fmtTime(a.first_seen)} · {ago(a.first_seen)}</span>
        </div>
        <h1>{a.card.headline}</h1>
        <p className="ink-2">{a.card.what_we_know}</p>
      </article>
    </Rephrasable>
  );
}

function CertIn({ a, className }) {
  const due = certinDue(a);
  if (!due) return null;
  return (
    <section className={`card dark ${className}`}>
      <span className="small on-dark-muted">Report to CERT-In by</span>
      <span className="big">{fmtTime(due)}</span>
      <span className="on-dark-muted"><TimeLeft toMs={due} /> · 6 hours from {fmtTime(a.first_seen)}</span>
      <span className="small on-dark-muted">Next step after the demo: a report drafted from this timeline, for you to check and send.</span>
    </section>
  );
}

function Checklist({ a, restore, busy, onTick, onRestore }) {
  const steps = a.card.steps;
  const tested = restoreSince(restore, a);
  const done = steps.filter((s) => s.done || (s.action === "VERIFY_BACKUP" && tested)).length;
  return (
    <section className="card" aria-label="What has to happen">
      <div className="row-between"><h2>What has to happen</h2><span className="small muted">{done} of {steps.length} done</span></div>
      <div>
        {steps.map((s) => {
          const isDone = s.done || (s.action === "VERIFY_BACKUP" && !!tested);
          return (
            <div key={s.action} className="list-row" style={{ justifyContent: "flex-start", alignItems: "flex-start", gap: 14, padding: "12px 0" }}>
              <button type="button" className="check" aria-pressed={isDone} aria-label={`Mark done: ${s.text}`} disabled={!!busy}
                style={{ cursor: "pointer", background: isDone ? "var(--green)" : "transparent", borderColor: isDone ? "var(--green)" : "#8A97A8", color: "#fff" }}
                onClick={() => onTick(s)}>
                {isDone ? <Check /> : null}
              </button>
              <span className="stack-sm grow" style={{ gap: 6 }}>
                <span>{s.text}</span>
                {s.action === "VERIFY_BACKUP" ? (
                  tested ? (
                    <span className="small" style={{ color: tested.result === "PASS" ? "var(--green-ink)" : "var(--red-ink)" }}>
                      <strong>{tested.result === "PASS" ? "Safe:" : "Not safe:"}</strong>{" "}
                      {Math.round(tested.backup_age_hours / 24)} days old · {tested.files_ok} of {tested.files_total} files intact
                      {tested.exposed ? " · always plugged in" : ""}. <Link to="/owner/readiness">See fixes</Link>
                    </span>
                  ) : (
                    <button type="button" className="btn btn-primary" style={{ alignSelf: "flex-start" }} disabled={!!busy} onClick={onRestore}>
                      {busy === "restore" ? "Testing the backup…" : "Test backup now"}
                    </button>
                  )
                ) : s.done && s.done_by ? <span className="small muted">{fmtTime(s.done_at)}</span> : null}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// IT support: Called → Picked up → Resolved → You confirmed. The owner verifies; IT doesn't close.
function ItCard({ a, clinic, busy, sendBack, setSendBack, onConfirm, onSendBack }) {
  const it = a.it;
  const who = clinic.clinic.it_contact_name;
  const stages = [["Called", it.called_at], ["Picked up", it.received_at], ["Resolved", it.resolved_at], ["You confirmed", it.closed_at]];
  const lastOn = stages.reduce((n, s, i) => (s[1] ? i : n), -1);
  const notes = it.log.filter((l) => l.kind === "note" && l.by_staff_id === null);
  const waitMin = it.called_at ? Math.floor((serverNow() - toMs(it.called_at)) / 60000) : 0;
  const editing = sendBack.id === a.id;

  let pill;
  let body;
  if (it.status === "none") {
    pill = <Pill tone="grey" noDot>Not called yet</Pill>;
    body = (
      <>
        <p className="ink-2">Nobody has called {who} yet. Staff are asked to call from their alert card.</p>
        <a className="btn btn-soft" style={{ alignSelf: "flex-start" }} href={`tel:${clinic.clinic.it_contact_phone}`}><Phone /> Call {who}</a>
      </>
    );
  } else if (it.status === "called") {
    pill = waitMin >= 10 ? <Pill tone="red">No answer for {waitMin} min</Pill> : <Pill tone="amber">Waiting for IT</Pill>;
    body = (
      <>
        <p className="ink-2">{staffName(clinic, it.called_by)} called at {fmtTime(it.called_at)}. {who} hasn't picked it up on ShieldMate yet.</p>
        {waitMin >= 10 ? <a className="btn btn-primary" style={{ alignSelf: "flex-start" }} href={`tel:${clinic.clinic.it_contact_phone}`}><Phone /> Call {who} yourself</a> : null}
      </>
    );
  } else if (it.status === "received") {
    pill = <Pill tone="amber">IT is on it</Pill>;
    body = (
      <>
        <p className="ink-2">{who} has been on it since {fmtTime(it.received_at)}.{it.sent_back_at ? ` You sent it back at ${fmtTime(it.sent_back_at)}.` : ""}</p>
        {notes.length ? <span className="small"><strong>Latest note:</strong> {notes[notes.length - 1].note}</span> : null}
      </>
    );
  } else if (it.status === "resolved") {
    pill = <Pill tone="blue">Check and close</Pill>;
    body = (
      <>
        <div className="callout blue" style={{ display: "block" }}>
          <span>{who} says it's fixed:</span>
          <p style={{ fontWeight: 400, margin: "6px 0 0" }}>“{it.resolved_note}”</p>
        </div>
        <span className="small ink-2">Before you confirm: ask the staff member whether the computer works normally, and check the steps above are done.</span>
        {editing ? (
          <>
            <label className="field-label" htmlFor={`sb-${a.id}`}>What's still wrong? (optional, {who} sees this)</label>
            <input className="it-note" style={{ minHeight: 52 }} id={`sb-${a.id}`} maxLength={200} autoComplete="off" autoFocus
              placeholder="e.g. Reception still can't open appointments" value={sendBack.text}
              onChange={(e) => setSendBack({ id: a.id, text: e.target.value })} />
            <div className="row">
              <button type="button" className="btn btn-primary" disabled={!!busy} onClick={onSendBack}>Send back to {who}</button>
              <button type="button" className="btn btn-ghost" onClick={() => setSendBack({ id: null, text: "" })}>Cancel</button>
            </div>
          </>
        ) : (
          <div className="row">
            <button type="button" className="btn btn-primary" disabled={!!busy} onClick={onConfirm}>Confirm it's fixed and close</button>
            <button type="button" className="btn btn-soft" onClick={() => setSendBack({ id: a.id, text: "" })}>Not fixed yet</button>
          </div>
        )}
      </>
    );
  } else {
    return null;
  }
  return (
    <section className="card" aria-label={`IT support for: ${a.card.headline}`}>
      <div className="row-between">
        <div className="stack-sm" style={{ gap: 2 }}>
          <h2>IT support · {who}</h2>
          <span className="small muted">For: {a.card.headline.replace(/\.$/, "")}</span>
        </div>
        {pill}
      </div>
      <div className="stages" role="img" aria-label={`IT progress: ${stages.filter((s) => s[1]).map((s) => s[0]).join(", ") || "not called yet"}`}>
        {stages.map(([label, at], i) => (
          <span key={label} className={`stage${at ? " on" : i === lastOn + 1 && lastOn >= 0 ? " wait" : ""}`}>
            <i />{label}
            {at ? <span className="small muted" style={{ fontWeight: 400 }}>{fmtTime(at)}</span> : null}
          </span>
        ))}
      </div>
      {body}
    </section>
  );
}

function ClosedToday({ closed, clinic }) {
  if (!closed.length) return null;
  return (
    <section className="card tight">
      <span className="section-label">Closed today</span>
      {closed.slice(0, 3).map((a) => (
        <div key={a.id} className="list-row" style={{ alignItems: "flex-start", flexDirection: "column", gap: 4 }}>
          <span className="row" style={{ gap: 8 }}><Pill tone="green" small>Closed</Pill><span className="bold">{a.card.headline.replace(/\.$/, "")}</span></span>
          <span className="small ink-2">Fixed by {clinic.clinic.it_contact_name}: {fixNote(a)} · you confirmed at {fmtTime(a.it.closed_at)}</span>
          {drillFor(a) ? <Link className="btn btn-ghost" style={{ paddingLeft: 0 }} to={`/owner/drill?scenario=${drillFor(a)}&alert=${a.id}`}>Practise this with the team</Link> : null}
        </div>
      ))}
    </section>
  );
}

function StandingRule({ clinic, busy, onToggle }) {
  const on = clinic.clinic.standing_rule_block_ip;
  return (
    <section className="card tight">
      <div className="row-between">
        <span className="bold">Standing rule</span>
        <Pill tone={on ? "green" : "grey"} small>{on ? "On" : "Off"}</Pill>
      </div>
      <span className="small ink-2">
        {on ? `If you don't answer a block request within ${clinic.clinic.approval_timeout_minutes} minutes, ShieldMate blocks the address for you.`
          : "If you don't answer a block request in time, ShieldMate asks your backup person instead of blocking."}
      </span>
      <button type="button" className="btn btn-soft" style={{ alignSelf: "flex-start" }} disabled={!!busy} onClick={onToggle}>
        {on ? "Turn off" : "Turn on"}
      </button>
    </section>
  );
}

function Activity({ events }) {
  if (!events.length) return null;
  return (
    <section className="card">
      <h2 style={{ fontSize: 18 }}>What happened</h2>
      <div className="timeline">
        {events.slice(0, 7).map((e, i) => (
          <div key={i} className="ev"><time>{fmtTime(e.at)}</time><FeedTag tag={e.tag} /><span>{e.text}</span></div>
        ))}
      </div>
    </section>
  );
}
