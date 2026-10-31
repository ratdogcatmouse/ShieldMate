import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getSimulate, getStatus, replay, reset, simulateStart, simulateStop } from "../api.js";
import { usePoll } from "../usePoll.js";
import { clearDrill, clearNotifSince, getBackstageToken, setBackstageToken, setStaff } from "../session.js";
import { track } from "../telemetry.js";
import { fmtTime } from "../format.js";
import { ErrorBanner } from "../components/Badge.jsx";

const REPLAYS = [
  ["password_guessing", "Password guessing", "Click 1 puts a card on Meena's phone and a request on Dr. Rao's. Click 2 raises the count."],
  ["ransomware", "Ransomware file changes", "One click: a ransomware card for staff and owner."],
];

// Attack-simulation scripts (backend/replay/sim/*.json). Needs the SIMULATE flag on the server.
const SIMS = [
  ["phish_owner", "Phishing aimed at the doctor's PC", "About 3 minutes. Shows how the team handles a phishing alert."],
  ["ransom_wave", "Ransomware wave", "About 5 minutes. Spreads from the reception PC to the file server unless the team contains it."],
  ["credential_sprawl", "Credential theft and lateral movement", "An attacker with a stolen password moves between computers."],
];

const SIM_STATUS_TEXT = {
  running: "Running",
  contained: "Contained by the team",
  spread: "The attack spread",
  stopped: "Stopped",
  expired: "Timed out",
};

export default function Backstage() {
  const [log, setLog] = useState([]);
  const [tokenDraft, setTokenDraft] = useState(getBackstageToken() || "");
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const timer = useRef(null);          // toast
  const confirmTimer = useRef(null);   // "Tap again to reset"; separate so a toast can't cancel it
  const status = usePoll(getStatus, 5000);
  // Simulation controls exist only with the SIMULATE flag on; off, the routes answer not_enabled.
  const simOn = status.data?.flags.SIMULATE === true;
  const sim = usePoll(simOn ? getSimulate : null, 2000, [simOn]);
  const simRun = sim.data?.run || null;
  const simRunning = simRun?.status === "running";
  // The server wants a token once BACKSTAGE_TOKEN is set; ask for it only when it says so.
  const needsToken = error && (error.error === "pin_required" || error.error === "pin_invalid");

  useEffect(() => {
    setStaff("backstage");
    return () => {
      clearTimeout(timer.current);
      clearTimeout(confirmTimer.current);
    };
  }, []);

  const say = (text) => {
    setToast(text);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), 3200);
  };

  const run = async (label, fn) => {
    setError(null);
    try {
      const res = await fn();
      setLog((prev) => [{ at: new Date().toISOString(), text: label }, ...prev].slice(0, 8));
      return res;
    } catch (e) {
      setError(e);
      return null;
    }
  };

  const doReplay = async (type) => {
    const r = await run(type, () => replay(type));
    if (r) say(`Injected: ${r.cards_created} card(s), ${r.filtered} filtered · ${r.clicks_left} click(s) left`);
  };

  const doSimStart = async (scriptId) => {
    const r = await run(`simulate ${scriptId}`, () => simulateStart(scriptId));
    if (r) say(`Attack started: ${r.title} · about ${Math.round(r.real_total_ms / 60000)} min`);
  };

  const doSimStop = async () => {
    const r = await run("simulate stop", simulateStop);
    if (r) say("Attack stopped");
  };

  const saveToken = () => {
    setBackstageToken(tokenDraft.trim());
    setError(null);
    say("Token saved. Try again.");
  };

  const doReset = async () => {
    if (!confirmReset) {
      track("ui.reset_armed");
      setConfirmReset(true);
      confirmTimer.current = setTimeout(() => setConfirmReset(false), 4000);
      return;
    }
    clearTimeout(confirmTimer.current);
    setConfirmReset(false);
    const r = await run("reset", reset);
    if (r) {
      clearDrill();
      clearNotifSince(); // the server counts notification IDs from 1 again
      say("Demo reset");
    }
  };

  const s = status.data;
  return (
    <div className="backstage">
      <ErrorBanner error={error} />
      <div className="inner">
        {needsToken && (
          <div className="bs-card">
            <input
              type="password"
              className="bs-input"
              aria-label="Backstage token"
              placeholder="Backstage token"
              value={tokenDraft}
              onChange={(e) => setTokenDraft(e.target.value)}
            />
            <button type="button" className="btn btn-bs" onClick={saveToken}>Save token</button>
          </div>
        )}
        <header className="stack-sm" style={{ gap: 4 }}>
          <span className="tiny bold" style={{ letterSpacing: "0.08em", color: "var(--night-muted)" }}>BACKSTAGE · NOT SHOWN TO JUDGES</span>
          <h1 style={{ fontSize: 24 }}>Demo controls</h1>
          <span className="small" style={{ color: "var(--night-muted)" }}>
            {s ? `${s.alert_source === "wazuh" ? "LIVE" : "Replay mode"} · actions ${s.flags.ACTIONS ? "on" : "off"} · AI reword ${s.flags.AI_REWORD ? "on" : "off"}` : "Connecting…"}
          </span>
        </header>

        {REPLAYS.map(([type, title, hint]) => (
          <div className="bs-card" key={type}>
            <div className="stack-sm" style={{ gap: 2 }}>
              <span className="bold">{title}</span>
              <span className="sub">{hint}</span>
            </div>
            <button type="button" className="btn btn-bs" onClick={() => doReplay(type)}>Replay next</button>
          </div>
        ))}

        {simOn && (
          <section className="bs-card" style={{ display: "block" }}>
            <span className="tiny bold" style={{ letterSpacing: "0.06em", color: "var(--night-muted)" }}>ATTACK SIMULATION</span>
            {SIMS.map(([id, title, hint]) => (
              <div className="row-between" key={id} style={{ marginTop: 12, gap: 12 }}>
                <div className="stack-sm" style={{ gap: 2 }}>
                  <span className="bold">{title}</span>
                  <span className="sub">{hint}</span>
                </div>
                <button type="button" className="btn btn-bs" disabled={simRunning} onClick={() => doSimStart(id)}>
                  Start
                </button>
              </div>
            ))}
            <div className="row-between" style={{ marginTop: 12, gap: 12 }}>
              <span className="small" style={{ color: "var(--night-muted)" }}>
                {simRun
                  ? `${SIM_STATUS_TEXT[simRun.status] || simRun.status} · ${simRun.script_id}${simRun.outcome_reason ? ` · ${simRun.outcome_reason}` : ""}`
                  : "No attack has been run yet"}
              </span>
              <button type="button" className="btn btn-bs-danger" disabled={!simRunning} onClick={doSimStop}>
                Stop attack
              </button>
            </div>
          </section>
        )}

        <section className="bs-card" style={{ display: "block" }}>
          <span className="tiny bold" style={{ letterSpacing: "0.06em", color: "var(--night-muted)" }}>THIS SESSION</span>
          <div className="bs-log">
            {log.length ? log.map((l, i) => <div key={i}>{fmtTime(l.at)}  {l.text}</div>) : "Nothing yet"}
          </div>
        </section>

        <div className="row-between" style={{ borderTop: "1px solid #2B3A5C", paddingTop: 16 }}>
          <span className="small" style={{ color: "var(--night-muted)" }}>Clears alerts, drills and backup tests. Run before every rehearsal.</span>
          <button type="button" className="btn btn-bs-danger" onClick={doReset}>
            {confirmReset ? "Tap again to reset" : "Reset demo"}
          </button>
        </div>

        <div className="row">
          <Link className="btn btn-soft" to="/">Start screen</Link>
          <Link className="btn btn-soft" to="/owner">Owner</Link>
        </div>
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
