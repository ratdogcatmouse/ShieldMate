// Labels and banners. Everything is rendered as plain text nodes.
export function Pill({ tone = "grey", dot = true, small, children }) {
  return (
    <span className={`pill pill-${tone}${dot ? "" : " no-dot"}${small ? " pill-sm" : ""}`}>{children}</span>
  );
}

// How much is at risk (backend impact priority). `impact` is {level, score, reason} or null.
const IMPACT_TONE = { low: "grey", medium: "amber", high: "red", critical: "red" };
const IMPACT_LABEL = { low: "Low impact", medium: "Medium impact", high: "High impact", critical: "Critical impact" };
export function ImpactPill({ impact }) {
  if (!impact) return null;
  return (
    <Pill tone={IMPACT_TONE[impact.level] || "grey"} small>
      {IMPACT_LABEL[impact.level] || impact.level}
    </Pill>
  );
}

export const SimulatedPill = () => <span className="pill pill-sim">Simulated action</span>;
export const SimulatedBackupPill = () => <span className="pill pill-sim">Simulated backup</span>;

// "Replay mode" while alert_source is replay, "LIVE" in live mode.
export function ModeBanner({ status, mock }) {
  const live = status?.alert_source === "wazuh";
  if (!status && !mock) return null;
  const mode = !status ? "" : live ? "LIVE" : "Replay mode";
  const text = [mock ? "Demo data" : null, mode || null].filter(Boolean).join(" · ");
  return <div className={`mode-banner${live ? " live" : ""}`}>{text}</div>;
}

// Shows `message`; an unknown error code never crashes a screen.
export function ErrorBanner({ error }) {
  if (!error) return null;
  return (
    <div className="error-banner" role="alert">
      {String(error.message || "Something went wrong.")}
    </div>
  );
}

export function StaleBanner({ stale }) {
  if (!stale) return null;
  return <div className="stale-banner">Can't reach the server. Showing the last update.</div>;
}

export function PracticeBanner({ children }) {
  return (
    <div className="practice-banner" role="note">
      {children || "PRACTICE · nothing here is real"}
    </div>
  );
}
