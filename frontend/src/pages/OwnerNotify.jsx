// Owner phone: what an approval request looks like as a lock-screen notification.
// A preview page: real push notifications come after the demo.
import { Link } from "react-router-dom";
import { ShieldPlain } from "../components/Icons.jsx";
import { useAction } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { decideBy, ownerOf } from "../lib/derive.js";
import { hideBlockDuplicates } from "../lib/notifications.js";
import { ago, fmtDate, fmtTime, useNow } from "../lib/time.js";
import { usePoll } from "../lib/usePoll.js";

function AppRow({ when }) {
  return (
    <div className="row" style={{ gap: 8 }}>
      <span className="app-icon"><ShieldPlain style={{ width: 16, height: 16 }} /></span>
      <span className="small bold">ShieldMate</span>
      <span className="tiny muted" style={{ marginLeft: "auto" }}>{when}</span>
    </div>
  );
}

export default function OwnerNotify() {
  const now = useNow();
  const [run, busy] = useAction();
  const { data, refresh } = usePoll(async () => {
    const [clinic, actions, list, notes] = await Promise.all([
      api.getClinic(),
      api.listOrEmpty(api.getActions(), "actions"),
      api.getAlerts("owner"),
      api.getNotifications("owner"),
    ]);
    return { clinic, actions, alerts: list.alerts, notes: notes.notifications };
  }, 2000);

  const pending = data?.actions.find((a) => a.status === "proposed");
  const done = data?.actions.find((a) => a.status === "executed");
  const alert = pending && data.alerts.find((a) => a.id === pending.alert_id);
  const clock = new Date(now).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata" }).replace(/\s?(am|pm)/i, "");

  return (
    <div className="lock">
      <div className="inner" aria-live="polite">
        <div className="clock">
          <div style={{ color: "#C9D6E8" }}>{fmtDate(now)}</div>
          <div className="t">{clock}</div>
        </div>
        {!data ? null : pending ? (
          <article className="notif" aria-label="ShieldMate notification">
            <AppRow when="now" />
            <span className="bold" style={{ fontSize: 18, lineHeight: 1.3 }}>Block an attacker on the reception computer?</span>
            <span className="ink-2">
              Someone has tried {alert ? `${alert.count}+` : "several"} wrong passwords.{" "}
              {pending.on_timeout === "block_under_standing_rule"
                ? `Your standing rule blocks them at ${fmtTime(decideBy(pending, data.clinic))} if you don't answer.`
                : `Answer by ${fmtTime(decideBy(pending, data.clinic))}.`}
            </span>
            <div className="btn-group">
              <button type="button" className="btn btn-primary" disabled={!!busy}
                onClick={() => run("approve", async () => { await api.approve(pending.id, ownerOf(data.clinic).id); await refresh(); })}>
                Approve
              </button>
              <Link className="btn btn-soft" to="/owner">Open</Link>
            </div>
            <span className="tiny muted">After the demo, Approve will ask for your fingerprint or PIN.</span>
          </article>
        ) : done ? (
          <article className="notif">
            <AppRow when={fmtTime(done.decided_at)} />
            <span className="bold">Blocked {done.target_ip}</span>
            <span className="ink-2">The reception computer is protected until {fmtTime(done.expires_at)}.</span>
            <Link className="btn btn-soft" to="/owner">Open ShieldMate</Link>
          </article>
        ) : (
          <article className="notif faded">
            <span className="bold">No requests right now</span>
            <span className="small" style={{ color: "#C9D6E8" }}>In Backstage, replay the password attack to see the approval request arrive here.</span>
            <Link className="btn btn-light" to="/backstage">Open Backstage</Link>
          </article>
        )}
        {/* A note about a block that is still pending is the approval card above; don't say it twice. */}
        {data && hideBlockDuplicates(data.notes, data.actions).slice(-2).reverse().map((n) => (
          <article key={n.id} className="notif faded">
            <div className="row tiny" style={{ color: "#C9D6E8" }}>
              <span className="bold">ShieldMate</span><span style={{ marginLeft: "auto" }}>{ago(n.created_at, now)}</span>
            </div>
            <span>{n.text}</span>
          </article>
        ))}
        <Link to="/owner" style={{ color: "#C9D6E8", textAlign: "center", marginTop: 8 }}>Back to the owner screens</Link>
      </div>
    </div>
  );
}
