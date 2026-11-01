// "Who's using this device?" Pick once; the address (/staff/1, /owner, /it) remembers.
// Presenter screens (projector, Backstage, every screen) sit in a closed section at the bottom.
import { Link } from "react-router-dom";
import { Chevron, Shield } from "../components/Icons.jsx";
import { StaleBanner } from "../components/ui.jsx";
import { getClinic, getStatus } from "../lib/api.js";
import { ROLE_LABEL } from "../lib/content.js";
import { sourceBadge } from "../lib/derive.js";
import { track } from "../lib/telemetry.js";
import { usePoll } from "../lib/usePoll.js";

async function load() {
  const [clinic, status] = await Promise.all([getClinic(), getStatus()]);
  return { clinic, status };
}

function RoleLink({ to, name, sub, role }) {
  return (
    <Link className="role-link" to={to} onClick={() => track("ui.person_picked", { role }, null)}>
      <span className="av" aria-hidden="true">{name.replace("Dr. ", "").charAt(0)}</span>
      <span className="stack-sm grow" style={{ gap: 0 }}>
        <span className="bold">{name}</span>
        <span className="small muted">{sub}</span>
      </span>
      <span style={{ color: "var(--muted)", display: "flex" }}><Chevron /></span>
    </Link>
  );
}

export default function Start() {
  const { data, stale } = usePoll(load, 10000);
  const c = data?.clinic;
  const people = c ? c.staff : [];
  const badge = data ? sourceBadge(data.status) : null;
  return (
    <div className="shell">
      <StaleBanner stale={stale} />
      <header className="topbar">
        <div className="row" style={{ gap: 10 }}>
          <span style={{ color: "var(--blue)", display: "flex" }}><Shield style={{ width: 24, height: 24 }} /></span>
          <span className="who">
            <span className="app-name">ShieldMate</span>
            <span className="tiny muted">{c ? c.clinic.name : "Loading…"}</span>
          </span>
        </div>
      </header>

      <main className="content">
        <div className="stack-sm">
          <h1 style={{ fontSize: 24 }}>Who's using this device?</h1>
          <p className="muted">Choose once. This address remembers.</p>
          {badge ? (
            <span className="status-line" role="status">
              <span className={`h-dot${badge.tone === "red" ? " bad" : ""}`} aria-hidden="true" />
              Monitoring {c.devices.length} computers · {badge.text}
            </span>
          ) : null}
        </div>

        <nav aria-label="Choose who you are" className="role-list">
          {people.map((p) =>
            p.role === "owner" ? (
              <RoleLink key={p.id} to="/owner" name={p.name} sub="Owner · laptop or phone" role="owner" />
            ) : (
              <RoleLink key={p.id} to={`/staff/${p.id}`} name={p.name} sub={`${ROLE_LABEL[p.role]} · phone`} role={p.role} />
            ),
          )}
          {c ? <RoleLink to="/it" name={c.clinic.it_contact_name} sub="IT support · laptop or phone" role="it" /> : null}
        </nav>

        <section className="card tight">
          <span className="section-label">Open on another phone</span>
          <p className="small">Join the same Wi-Fi or hotspot as this laptop, then open:</p>
          <p className="mono" style={{ fontSize: 16, wordBreak: "break-all" }}>{window.location.origin}</p>
        </section>

        <details className="log">
          <summary>Presenter tools</summary>
          <div className="body small">
            <Link className="btn btn-soft btn-block" to="/mission">Operations view (projector)</Link>
            <Link className="btn btn-soft btn-block" to="/backstage">Presenter controls</Link>
            <span className="section-label" style={{ marginTop: 8 }}>All screens</span>
            {people.filter((p) => p.role !== "owner").slice(0, 1).map((p) => (
              <span key={p.id} className="stack-sm" style={{ gap: 6 }}>
                <Link to={`/staff/${p.id}`}>Staff · Today and the alert card (after Presenter controls → password attack)</Link>
                <Link to={`/staff/${p.id}/drill`}>Staff · Join a drill, lobby, steps and debrief</Link>
              </span>
            ))}
            <Link to="/owner/notify">Owner phone · Approval notification</Link>
            <Link to="/owner">Owner · Right now (live approval or ransomware)</Link>
            <Link to="/owner/readiness">Owner · Readiness</Link>
            <Link to="/owner/drill">Owner · Hosting a drill</Link>
            <Link to="/it">IT support · incidents, call received, resolved</Link>
            <span className="muted">Owner pages switch to the phone layout below 900 px wide.</span>
          </div>
        </details>
      </main>
    </div>
  );
}
