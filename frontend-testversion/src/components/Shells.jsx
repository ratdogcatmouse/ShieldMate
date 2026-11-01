// Page frames: the owner's sidebar (laptop) / bottom tabs (phone), and the staff phone's tabs.
import { NavLink } from "react-router-dom";
import { Bars, History, Home, Menu, Shield, ShieldPlain, Target } from "./Icons.jsx";
import { getStatus } from "../lib/api.js";
import { healthRows } from "../lib/derive.js";
import { fmtTime } from "../lib/time.js";
import { usePoll } from "../lib/usePoll.js";
import { StaleBanner } from "./ui.jsx";

const OWNER_PAGES = [
  ["/owner", "Right now"],
  ["/owner/readiness", "Readiness"],
  ["/owner/drill", "Drills"],
  ["/owner/notify", "Phone alert preview"],
  ["/mission", "Operations view (projector)"],
];

// `urgent` puts a red dot on "Right now" (something needs the owner's decision).
// The sidebar also shows system health (alert source, Wazuh API and indexer) from GET /status.
export function OwnerShell({ clinicName, ownerName, urgent, stale, children }) {
  const { data: status } = usePoll(getStatus, 10000);
  return (
    <div className="owner">
      <nav className="sidebar" aria-label="Main">
        <div className="brand">
          <span style={{ color: "var(--blue)", display: "flex" }}><Shield /></span>
          <span className="stack-sm" style={{ gap: 0 }}>
            <span className="brand-name">ShieldMate</span>
            <span className="tiny muted">{clinicName}</span>
          </span>
        </div>
        {OWNER_PAGES.map(([to, label]) => (
          <NavLink key={to} className="nav" to={to} end>
            {label}
            {to === "/owner" && urgent ? <span className="dot" aria-label="Needs you" /> : null}
          </NavLink>
        ))}
        <div className="foot">
          {status ? (
            <section className="sys-health" aria-label="System health">
              <span className="section-label">System health</span>
              {healthRows(status).map(([k, v, st]) => (
                <span key={k} className="h-row"><span>{k}</span>
                  <span className="row" style={{ gap: 6, flexWrap: "nowrap" }}><span className={`h-dot ${st}`} aria-hidden="true" /><span className="ink-2">{v}</span></span>
                </span>
              ))}
              <span className="h-row"><span>Server time</span><span className="mono ink-2">{fmtTime(status.server_time)}</span></span>
            </section>
          ) : null}
          <span>{ownerName ? `${ownerName} · owner` : "Owner"}</span>
          <NavLink to="/">Switch person</NavLink>
          <NavLink to="/backstage">Presenter controls</NavLink>
        </div>
      </nav>
      <div className="owner-main">
        <StaleBanner stale={stale} />
        <main className="owner-body" aria-live="polite">{children}</main>
        <nav className="tabbar" aria-label="Main">
          <NavLink to="/owner" end><ShieldPlain className="" />Right now</NavLink>
          <NavLink to="/owner/readiness"><Bars className="" />Readiness</NavLink>
          <NavLink to="/owner/drill"><Target className="" />Drills</NavLink>
          <NavLink to="/" end><Menu className="" />Switch</NavLink>
        </nav>
      </div>
    </div>
  );
}

// The staff phone's bottom tabs (NavLink marks the current one with aria-current="page").
export function StaffTabs({ staffId }) {
  return (
    <nav className="tabbar" aria-label="Main">
      <NavLink to={`/staff/${staffId}`} end><Home className="" />Today</NavLink>
      <NavLink to={`/staff/${staffId}/drill`}><Target className="" />Drills</NavLink>
      <NavLink to={`/staff/${staffId}/history`}><History className="" />History</NavLink>
      <NavLink to="/" end><Menu className="" />Switch</NavLink>
    </nav>
  );
}
