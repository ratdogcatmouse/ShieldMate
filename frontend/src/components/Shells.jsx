import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { API_MODE, getStatus } from "../api.js";
import { usePoll } from "../usePoll.js";
import { getStaff } from "../session.js";
import { Icon } from "../icons.jsx";
import { ModeBanner } from "./Badge.jsx";

const mock = API_MODE === "mock";

export function Topbar({ left, right }) {
  return (
    <header className="topbar">
      {left || (
        <div className="row" style={{ gap: 8 }}>
          <span className="brand-mark"><Icon name="shield" size={28} /></span>
          <span className="app-name">ShieldMate</span>
        </div>
      )}
      {right}
    </header>
  );
}

function Tab({ to, icon, label, end }) {
  return (
    <NavLink to={to} end={end}>
      <Icon name={icon} className="" />
      {label}
    </NavLink>
  );
}

// Phone-first shell: Start, Staff and Drill.
export function PhoneShell() {
  const { data: status } = usePoll(getStatus, 5000);
  const { pathname } = useLocation();
  const me = getStaff();
  const showTabs = pathname.startsWith("/staff/") || pathname.startsWith("/drill/");
  const home = me && me !== "backstage" ? (me.role === "owner" ? "/owner" : `/staff/${me.id}`) : "/";
  return (
    <div className="shell">
      <ModeBanner status={status} mock={mock} />
      <Outlet />
      {showTabs && (
        <nav className="tabbar" aria-label="Main" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <Tab to={home} icon="home" label="Today" end />
          <Tab to="/" icon="menu" label="Switch" end />
        </nav>
      )}
    </div>
  );
}

// Owner: side menu on a laptop, bottom tabs under 900 px.
// READINESS_PAGE and NOTIFY_PREVIEW (features.js) would add menu entries here. Not built.
export function OwnerShell() {
  const { data: status } = usePoll(getStatus, 5000);
  return (
    <div className="owner">
      <nav className="sidebar" aria-label="Main">
        <div className="brand">
          <span className="brand-mark"><Icon name="shield" /></span>
          <span className="stack-sm" style={{ gap: 0 }}>
            <span className="brand-name">ShieldMate</span>
            <span className="tiny muted">Sunrise Family Clinic</span>
          </span>
        </div>
        <NavLink className="nav" to="/owner" end>Right now</NavLink>
        <div className="foot">
          <span>Dr. Rao · owner</span>
          <Link to="/">Switch person</Link>
          <Link to="/backstage">Backstage</Link>
        </div>
      </nav>
      <div className="owner-main">
        <ModeBanner status={status} mock={mock} />
        <Outlet />
        <nav className="tabbar" aria-label="Main" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <Tab to="/owner" icon="shieldNav" label="Right now" end />
          <Tab to="/" icon="menu" label="Switch" end />
        </nav>
      </div>
    </div>
  );
}

