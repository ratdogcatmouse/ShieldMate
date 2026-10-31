import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  API_MODE, approve, createDrill, decline, getActions, getAlerts, getClinic, getDevices,
  getNotifications, getRestoreLatest, getStatus, runRestore,
} from "../api.js";
import { usePoll } from "../usePoll.js";
import { getLang, setDrill } from "../session.js";
import { fmtTime } from "../format.js";
import { Icon } from "../icons.jsx";
import ApprovalCard, { DecidedCard } from "../components/ApprovalCard.jsx";
import DeviceStrip from "../components/DeviceStrip.jsx";
import RestoreResult from "../components/RestoreResult.jsx";
import { ErrorBanner, Pill, StaleBanner } from "../components/Badge.jsx";

function AlertBlock({ alert, onPractise, restore, onRestore, restoring }) {
  const { card } = alert;
  const incident = alert.rule_id === "100201";
  return (
    <>
      <article className="card">
        <div className="row">
          <Pill tone="red">Needs you now</Pill>
          <span className="small muted">Started {fmtTime(alert.first_seen)}</span>
        </div>
        <h1>{card.headline}</h1>
        <p className="ink-2">{card.what_we_know}</p>
        <p className="small muted">{card.why}</p>
      </article>
      {card.steps.length > 0 && (
        <section className="card" aria-label="What has to happen">
          <h2>What has to happen</h2>
          {/* STEP_TICKING slot (features.js): owner checklist ticking goes here. Not built. */}
          {card.steps.map((s, i) => (
            <div key={`${s.action}-${i}`} className="list-row" style={{ justifyContent: "flex-start", alignItems: "flex-start", gap: 14, padding: "12px 0" }}>
              <span className="check" aria-hidden="true">{i + 1}</span>
              <span className="stack-sm grow" style={{ gap: 6 }}>
                <span>{s.text}</span>
                {s.action === "VERIFY_BACKUP" && (
                  <button type="button" className="btn btn-primary" style={{ alignSelf: "flex-start" }} disabled={restoring} onClick={onRestore}>
                    {restoring ? "Testing the backup…" : "Test backup now"}
                  </button>
                )}
              </span>
            </div>
          ))}
        </section>
      )}
      {incident && restore && restore.result !== "NOT_TESTED" && <RestoreResult run={restore} />}
      {card.drill_scenario && (
        <section className="card tight">
          <span className="section-label">Practise what just happened</span>
          <div className="row-between">
            <span>{card.headline.replace(/\.$/, "")}</span>
            <button type="button" className="btn btn-ghost" onClick={onPractise}>Practise this with the team</button>
          </div>
        </section>
      )}
    </>
  );
}

export default function Owner() {
  const navigate = useNavigate();
  const lang = getLang();
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [actionError, setActionError] = useState(null);

  const clinic = usePoll(getClinic, 30000);
  const alerts = usePoll(() => getAlerts("owner", lang), 2000, [lang]);
  const notifs = usePoll(() => getNotifications("owner", null, 0), 2000);
  const restore = usePoll(getRestoreLatest, 2000);
  const status = usePoll(getStatus, 5000);

  // Actions and devices exist only with the ACTIONS flag on; off, they answer not_enabled.
  const actionsOn = status.data?.flags.ACTIONS === true;
  const actions = usePoll(actionsOn ? () => getActions() : null, 2000, [actionsOn]);
  const devices = usePoll(actionsOn ? getDevices : null, 2000, [actionsOn]);

  const owner = clinic.data?.staff.find((s) => s.role === "owner");
  const list = alerts.data?.alerts || [];
  const openAlerts = list.filter((a) => a.status === "new");
  const actionFor = (alertId) => actions.data?.actions.find((a) => a.alert_id === alertId);
  const urgent = openAlerts.length > 0;

  const guard = async (fn, setter = setBusy) => {
    setter(true);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e);
    } finally {
      setter(false);
    }
  };

  const practise = (alert) =>
    guard(async () => {
      const res = await createDrill(alert.card.drill_scenario, owner.id, alert.id);
      setDrill({ code: res.code, player_id: res.player_id });
      navigate(`/drill/${res.code}`);
    });
  const startDrill = () =>
    guard(async () => {
      const res = await createDrill("ransomware_clinic", owner.id, null);
      setDrill({ code: res.code, player_id: res.player_id });
      navigate(`/drill/${res.code}`);
    });

  const modePill = (
    <Pill tone="accent" small>
      {API_MODE === "mock" ? "Demo data · " : ""}
      {status.data?.alert_source === "wazuh" ? "Live" : "Replay mode"}
    </Pill>
  );

  return (
    <>
      <ErrorBanner error={actionError || alerts.error || restore.error || status.error} />
      <StaleBanner stale={alerts.stale || restore.stale || status.stale} />
      <main className="owner-body" aria-live="polite">
        <div className="owner-head">
          <div>
            <span className="owner-mobile-head">{clinic.data?.clinic.name}</span>
            <h1>Right now</h1>
          </div>
          {modePill}
        </div>
        {/* ACTIVITY_FEED slot (features.js): "What happened" timeline goes in the side column. Not built. */}
        {/* READINESS_PAGE slot (features.js): readiness report with a menu entry in Shells.jsx. Not built. */}
        <div className="cols">
          <div className="col-main">
            {openAlerts.map((a) => {
              const act = actionFor(a.id);
              return (
                <div key={a.id} className="stack">
                  {act?.status === "proposed" && (
                    <ApprovalCard
                      action={act}
                      alert={a}
                      standingRule={clinic.data?.clinic.standing_rule_block_ip}
                      busy={busy}
                      onApprove={() => guard(() => approve(act.id, owner.id))}
                      onDecline={() => guard(() => decline(act.id, owner.id))}
                    />
                  )}
                  {act && act.status !== "proposed" && <DecidedCard action={act} />}
                  <AlertBlock
                    alert={a}
                    restore={restore.data}
                    restoring={restoring}
                    onRestore={() => guard(runRestore, setRestoring)}
                    onPractise={() => practise(a)}
                  />
                </div>
              );
            })}
            {!urgent && alerts.data && (
              <section className="card">
                <span className="ok-icon"><Icon name="shield" size={28} /></span>
                <h1>All clear</h1>
                <p className="ink-2">
                  Nothing needs you right now. ShieldMate is watching {clinic.data?.devices.length ?? "the"} computers
                  {alerts.data.hidden_count > 0 ? ` and has hidden ${alerts.data.hidden_count} routine events today` : ""}.
                </p>
                <span className="small muted">Use Backstage to replay an attack for the demo.</span>
              </section>
            )}
            <section className="card tight">
              <span className="section-label">Team practice</span>
              <div className="row-between">
                <span>Ransomware drill · about 6 minutes</span>
                <button type="button" className="btn btn-primary" disabled={busy || !owner} onClick={startDrill}>
                  Start team drill
                </button>
              </div>
            </section>
          </div>
          <aside className="col-side">
            <DeviceStrip devices={devices.data?.devices || clinic.data?.devices || []} />
            {restore.data && !openAlerts.some((a) => a.rule_id === "100201") && <RestoreResult run={restore.data} />}
            {notifs.data?.notifications.length > 0 && (
              <section className="card">
                <h2 style={{ fontSize: 18 }}>Updates from the team</h2>
                <div className="timeline">
                  {notifs.data.notifications.map((n) => (
                    <div className="ev" key={n.id}>
                      <time>{fmtTime(n.created_at)}</time>
                      <span>{n.text}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </aside>
        </div>
      </main>
    </>
  );
}
