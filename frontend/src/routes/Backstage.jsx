import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getStatus, replay, reset } from "../api.js";
import { usePoll } from "../usePoll.js";
import { clearDrill, clearNotifSince, setStaff } from "../session.js";
import { fmtTime } from "../format.js";
import { ErrorBanner } from "../components/Badge.jsx";

const REPLAYS = [
  ["password_guessing", "Password guessing", "Click 1 puts a card on Meena's phone and a request on Dr. Rao's. Click 2 raises the count."],
  ["ransomware", "Ransomware file changes", "One click: a ransomware card for staff and owner."],
];

export default function Backstage() {
  const [log, setLog] = useState([]);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const timer = useRef(null);
  const status = usePoll(getStatus, 5000);

  useEffect(() => {
    setStaff("backstage");
    return () => clearTimeout(timer.current);
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

  const doReset = async () => {
    if (!confirmReset) {
      setConfirmReset(true);
      timer.current = setTimeout(() => setConfirmReset(false), 4000);
      return;
    }
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
