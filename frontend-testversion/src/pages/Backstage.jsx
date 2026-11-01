// Backstage: demo controls. Not shown to the audience.
import { useState } from "react";
import { Link } from "react-router-dom";
import { StaleBanner, useAction, useToast } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { clearSeen, getBackstageToken, setBackstageToken } from "../lib/session.js";
import { track } from "../lib/telemetry.js";
import { fmtTime, serverNow, syncServerTime } from "../lib/time.js";
import { usePoll } from "../lib/usePoll.js";
import { simResult } from "../lib/derive.js";

const REPLAYS = [
  ["password_guessing", "Password guessing", (n) => n === 0
    ? "Next: click 1 · card on the front desk phones, approval request for the owner"
    : "Next: click 2 · count goes from 8+ to 12+ (same card, or it reopens a \"That was me\")"],
  ["ransomware", "Ransomware file changes", () => "Next: click 1 · ransomware card for the owner"],
];
const SCRIPTS = [
  ["ransom_wave", "Ransomware wave: reception PC to the file server"],
  ["phish_owner", "Phishing aimed at the doctor's PC"],
  ["credential_sprawl", "Credential theft and lateral movement"],
  // v4: the three new drills' attacks. Ticking the right card step stops them.
  ["phish_doctor_email", "Fake invoice email, account taken over · stop: change password"],
  ["tech_support_call", "Fake tech-support call, remote control · stop: unplug the network"],
  ["supplier_bank_fraud", "Fake supplier bank details (demo only) · stop: call back to check"],
];

export default function Backstage() {
  const [run, busy] = useAction();
  const toast = useToast();
  const [armed, setArmed] = useState(false);
  const [clicks, setClicks] = useState({});            // replay type -> {done, left}
  const [log, setLog] = useState([]);
  const [token, setToken] = useState(getBackstageToken() || "");
  const { data, stale, refresh } = usePoll(async () => {
    const [status, clinic] = await Promise.all([api.getStatus(), api.getClinic()]);
    const sim = status.flags.SIMULATE ? (await api.getSimulate()).run : null;
    return { status, clinic, sim };
  }, 2000);

  const note = (text) => setLog((l) => [{ at: serverNow(), text }, ...l].slice(0, 12));
  const doReplay = (type) => run(`replay-${type}`, async () => {
    const r = await api.replay(type);
    setClicks((c) => ({ ...c, [type]: { done: r.click, left: r.clicks_left } }));
    note(`${type} click ${r.click} → ${r.cards_created} new card(s), ${r.grouped} grouped, ${r.filtered} filtered`);
    toast(`Injected ${type.replace("_", " ")} click ${r.click}`);
    await refresh();
  });
  const doSkip = () => run("skip", async () => {
    const r = await api.skip(5);
    syncServerTime(r.server_time);
    note(`skipped ahead 5 min (clock is ${r.offset_minutes} min ahead)`);
    toast("Clock moved 5 minutes ahead");
    await refresh();
  });
  const doReset = () => {
    if (!armed) {
      track("ui.reset_armed");
      setArmed(true);
      setTimeout(() => setArmed(false), 4000);
      return;
    }
    setArmed(false);
    run("reset", async () => {
      const r = await api.reset();
      syncServerTime(r.reset_at);
      clearSeen();
      setClicks({});
      note("demo reset");
      toast("Demo reset");
      await refresh();
    });
  };
  const doSim = (scriptId) => run(`sim-${scriptId}`, async () => {
    const r = await api.simulateStart(scriptId);
    note(`simulation started: ${r.title}`);
    await refresh();
  });
  const stopSim = () => run("sim-stop", async () => { await api.simulateStop(); note("simulation stopped"); await refresh(); });

  const st = data?.status;
  const simOn = !!st?.flags.SIMULATE;
  const teamSees = st ? simResult(st.simulation, data.clinic) : null;   // what the phones show after a run
  const firstStaff = data?.clinic.staff.find((s) => s.role !== "owner");
  return (
    <div className="backstage">
      <StaleBanner stale={stale} />
      <main className="inner" aria-live="polite">
        <header className="stack-sm" style={{ gap: 4 }}>
          <span className="tiny bold" style={{ letterSpacing: "0.08em", color: "#9DB4D3" }}>PRESENTER CONTROLS · NOT SHOWN TO THE AUDIENCE</span>
          <h1 style={{ fontSize: 24 }}>Demo controls</h1>
          <span className="small" style={{ color: "#B7C6DA" }}>
            {st ? `Alerts from ${st.alert_source === "wazuh" ? "Wazuh (live)" : "the recorded replay"} · server time ${fmtTime(st.server_time)}` : "Talking to the ShieldMate server…"}
          </span>
        </header>

        {st?.alert_source === "wazuh" ? (
          <div className="bs-card">
            <div className="stack-sm" style={{ gap: 2 }}>
              <span className="bold">{st.wazuh.api_ok && st.wazuh.indexer_ok ? "Wazuh: connected" : st.wazuh.api_ok === false || st.wazuh.indexer_ok === false ? "Wazuh: not reachable" : "Wazuh: connecting…"}</span>
              <span className="sub">
                {st.wazuh.last_alert_at ? `Last alert ${fmtTime(st.wazuh.last_alert_at)}. ` : ""}
                If it's down, use Replay below and say "recorded from our lab".
              </span>
            </div>
            <span className={`pill ${st.wazuh.api_ok && st.wazuh.indexer_ok ? "pill-green" : "pill-red"}`}>{st.wazuh.api_ok && st.wazuh.indexer_ok ? "Live" : "Off"}</span>
          </div>
        ) : null}

        {REPLAYS.map(([type, title, next]) => {
          const c = clicks[type];
          const exhausted = c && c.left === 0;
          return (
            <div key={type} className="bs-card">
              <div className="stack-sm" style={{ gap: 2 }}>
                <span className="bold">{title}</span>
                <span className="sub">{exhausted ? "Already replayed · Reset to run again" : next(c ? c.done : 0)}</span>
              </div>
              <button type="button" className="btn btn-bs" disabled={!!busy || exhausted} onClick={() => doReplay(type)}>Replay next</button>
            </div>
          );
        })}

        <div className="bs-card">
          <div className="stack-sm" style={{ gap: 2 }}>
            <span className="bold">Skip ahead 5 minutes</span>
            <span className="sub">Shows the standing rule acting when nobody answers{data?.clinic.clinic.standing_rule_block_ip ? "" : " (turn the rule on from the owner screen first)"}.</span>
          </div>
          <button type="button" className="btn btn-bs" disabled={!!busy} onClick={doSkip}>Skip 5 min</button>
        </div>

        {st ? (
          <section className="bs-card" style={{ display: "block" }} aria-label="Attack simulation">
            <span className="tiny bold" style={{ letterSpacing: "0.06em", color: "#9DB4D3" }}>ATTACK SIMULATION · TEST MODE</span>
            {simOn && data.sim && data.sim.status === "running" ? (
              <div className="row-between" style={{ marginTop: 8 }}>
                <span className="sub">Running {data.sim.script_id} · {data.sim.phases_fired} phases so far</span>
                <button type="button" className="btn btn-bs-danger" disabled={!!busy} onClick={stopSim}>Stop</button>
              </div>
            ) : (
              <div className="stack-sm" style={{ marginTop: 8 }}>
                {!simOn ? <span className="sub">Practice attacks are switched off. Start the server with SIMULATE=1 (in backend/.env) to run them.</span> : null}
                {simOn && data?.sim ? <span className="sub">Last run: {data.sim.script_id} · {data.sim.status}{data.sim.outcome_reason ? ` (${data.sim.outcome_reason})` : ""}</span> : null}
                {simOn && teamSees ? <span className="sub">Team sees: {teamSees.title}. {teamSees.line}</span> : null}
                {SCRIPTS.map(([id, title]) => (
                  <div key={id} className="row-between">
                    <span>{title}</span>
                    <button type="button" className="btn btn-bs" disabled={!!busy || !simOn} onClick={() => doSim(id)}>Play</button>
                  </div>
                ))}
              </div>
            )}
          </section>
        ) : null}

        <section className="bs-card" style={{ display: "block" }}>
          <span className="tiny bold" style={{ letterSpacing: "0.06em", color: "#9DB4D3" }}>THIS SESSION</span>
          <div className="bs-log">{log.length ? log.map((l, i) => <div key={i}>{fmtTime(l.at)}  {l.text}</div>) : "Nothing yet"}</div>
        </section>

        <div className="row-between" style={{ borderTop: "1px solid var(--night-line)", paddingTop: 16 }}>
          <span className="small" style={{ color: "#B7C6DA" }}>Clears alerts, drills and backup tests, and puts the clock back. Run before every rehearsal.</span>
          <button type="button" className="btn btn-bs-danger" disabled={busy === "reset"} onClick={doReset}>{armed ? "Tap again to reset" : "Reset demo"}</button>
        </div>

        <details className="log">
          <summary>Backstage token</summary>
          <div className="body">
            <span className="small" style={{ color: "#B7C6DA" }}>Only needed when the server has BACKSTAGE_TOKEN set. Kept for this tab only.</span>
            <div className="row">
              <input className="it-note" style={{ minHeight: 44, flex: 1 }} type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} aria-label="Backstage token" />
              <button type="button" className="btn btn-bs" onClick={() => { setBackstageToken(token); toast("Token saved for this tab"); }}>Save</button>
            </div>
          </div>
        </details>

        <div className="row">
          <Link className="btn btn-soft" to="/">Start screen</Link>
          <Link className="btn btn-soft" to="/owner">Owner</Link>
          {firstStaff ? <Link className="btn btn-soft" to={`/staff/${firstStaff.id}`}>{firstStaff.name}</Link> : null}
          <Link className="btn btn-soft" to="/it">IT support</Link>
          <Link className="btn btn-soft" to="/mission">Operations view</Link>
        </div>
      </main>
    </div>
  );
}
