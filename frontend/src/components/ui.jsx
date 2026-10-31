// Small shared pieces: toasts, the tap-action hook, pills and the per-second tickers.
import { createContext, useCallback, useContext, useRef, useState } from "react";
import { DEVICE_STATUS } from "../lib/content.js";
import { left, mmss, stopwatch, toMs, useNow } from "../lib/time.js";

// --- toasts -------------------------------------------------------------------

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const show = useCallback((text) => {
    const id = Math.random();
    setToasts((t) => [...t, { id, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toasts.map((t) => (
        <div key={t.id} className="toast" role="status">{t.text}</div>
      ))}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

// --- taps ------------------------------------------------------------------------

// useAction() -> [run, busy]. run(key, fn) runs one tap at a time: while it is busy `busy`
// holds its key (so that button can show "Testing…" and the others can be disabled), and a
// failure shows the server's message as a toast instead of breaking the screen.
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(null);
  const busyRef = useRef(null);
  const run = useCallback(async (key, fn) => {
    if (busyRef.current) return;
    busyRef.current = key;
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      toast(e?.message || "Something went wrong.");
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
  }, [toast]);
  return [run, busy];
}

// --- labels --------------------------------------------------------------------------

export function Pill({ tone, small, noDot, children, className = "" }) {
  return (
    <span className={`pill pill-${tone}${small ? " pill-sm" : ""}${noDot ? " no-dot" : ""} ${className}`.trim()}>
      {children}
    </span>
  );
}

// v4: how the team did against a practice attack (derive.simResult), on the owner and staff screens.
export function SimResult({ result }) {
  if (!result) return null;
  return (
    <section className="card tight" role="status" aria-label="Practice attack result">
      <Pill tone={result.tone} noDot={result.tone === "grey"}>Practice attack · {result.title}</Pill>
      <span className="bold">{result.what}</span>
      <span className="ink-2">{result.line}</span>
    </section>
  );
}

export function StatusPill({ status, label }) {
  const s = DEVICE_STATUS[status] || DEVICE_STATUS.ok;
  return <Pill tone={s.tone} small>{label || s.label}</Pill>;
}

// The small "LIVE · Wazuh" chip in front of a timeline line that came from the real Wazuh feed.
export function FeedTag({ tag }) {
  return tag ? <span className="feed-tag">{tag}</span> : null;
}

// "Couldn't reach the server" banner: the screen keeps its last good data underneath.
export function StaleBanner({ stale }) {
  if (!stale) return null;
  return <div className="mode-banner" role="status">Can't reach ShieldMate. Showing the last update; retrying…</div>;
}

// --- tickers (redraw every second from the server's clock) --------------------------

// m:ss until `to` (ISO).
export function Countdown({ to }) {
  const now = useNow();
  return <>{mmss(Math.round((toMs(to) - now) / 1000))}</>;
}

// "5 h 38 min left" until `toMs` (ms).
export function TimeLeft({ toMs: target }) {
  const now = useNow();
  return <>{left(target, now)}</>;
}

// mm:ss since `from` (ISO), frozen at `stop` once there is one.
export function Stopwatch({ from, stop }) {
  const now = useNow();
  const end = stop ? toMs(stop) : now;
  return <>{stopwatch(Math.round((end - toMs(from)) / 1000))}</>;
}

// Last drill vs today, as two bars. prev.seeded => labelled as sample data.
export function Retest({ prev, right, total }) {
  if (!prev) return null;
  const h = (r, t) => Math.max(8, Math.round(100 * (t ? r / t : 0)));
  const diff = right - prev.team_right;
  const label = prev.label.toLowerCase();
  return (
    <div className="stack-sm">
      <span className="section-label">{prev.label} vs today</span>
      <div className="bars">
        <div className="bar"><span>{prev.team_right}/{prev.team_total}</span><i style={{ height: h(prev.team_right, prev.team_total) }} /></div>
        <div className="bar now"><span style={{ color: "var(--blue)" }}>{right}/{total}</span><i style={{ height: h(right, total) }} /></div>
      </div>
      <div className="row-between small muted" style={{ justifyContent: "space-around" }}>
        <span>{prev.label}{prev.seeded ? " (sample data)" : ""}</span><span>Today</span>
      </div>
      <span className="bold">
        {diff > 0 ? `${diff} more right calls than ${label}` : diff === 0 ? `Same as ${label}` : `Fewer right calls than ${label}`}
      </span>
    </div>
  );
}
