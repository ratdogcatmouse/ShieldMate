// Page frames: the owner's sidebar (laptop) / bottom tabs (phone), and the staff phone's tabs.
import { NavLink } from "react-router-dom";
import { Bars, History, Home, Menu, Shield, ShieldPlain, Target } from "./Icons.jsx";
import { StaleBanner } from "./ui.jsx";

const OWNER_PAGES = [
  ["/owner", "Right now"],
  ["/owner/readiness", "Readiness"],
  ["/owner/drill", "Drills"],
  ["/owner/notify", "Phone alert preview"],
  ["/mission", "Mission control (projector)"],
];

// `urgent` puts a red dot on "Right now" (something needs the owner's decision).
export function OwnerShell({ clinicName, ownerName, urgent, stale, children }) {
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
          <span>{ownerName ? `${ownerName} · owner` : "Owner"}</span>
          <NavLink to="/">Switch person</NavLink>
          <NavLink to="/backstage">Backstage</NavLink>
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
