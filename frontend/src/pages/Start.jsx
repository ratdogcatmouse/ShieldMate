// "Who's using this device?" Pick once; the address (/staff/1, /owner, /it) remembers.
import { Link } from "react-router-dom";
import { Chevron, Shield } from "../components/Icons.jsx";
import { StaleBanner } from "../components/ui.jsx";
import { getClinic } from "../lib/api.js";
import { ROLE_LABEL } from "../lib/content.js";
import { track } from "../lib/telemetry.js";
import { usePoll } from "../lib/usePoll.js";

function RoleLink({ to, name, sub, role }) {
  return (
    <Link className="role-link" to={to} onClick={() => track("ui.person_picked", { role }, null)}>
      <span className="stack-sm" style={{ gap: 0 }}>
        <span className="bold">{name}</span>
        <span className="small muted">{sub}</span>
      </span>
      <span style={{ color: "var(--blue)" }}><Chevron /></span>
    </Link>
  );
}

export default function Start() {
  const { data: c, stale } = usePoll(getClinic, 10000);
  const people = c ? c.staff : [];
  return (
    <div className="shell">
      <StaleBanner stale={stale} />
      <header className="topbar">
        <div className="row" style={{ gap: 8 }}>
          <span style={{ color: "var(--blue)", display: "flex" }}><Shield style={{ width: 28, height: 28 }} /></span>
          <span className="app-name">ShieldMate</span>
        </div>
      </header>

      <main className="content">
        <div className="stack-sm">
          <h1 style={{ fontSize: 26 }}>Who's using this device?</h1>
          <p className="muted">{c ? c.clinic.name : "Loading…"}. Pick once; this address remembers.</p>
        </div>

        <nav aria-label="Choose who you are" className="stack-sm">
          {people.map((p) =>
            p.role === "owner" ? (
              <RoleLink key={p.id} to="/owner" name={p.name} sub="Owner · laptop or phone" role="owner" />
            ) : (
              <RoleLink key={p.id} to={`/staff/${p.id}`} name={p.name} sub={`${ROLE_LABEL[p.role]} · phone`} role={p.role} />
            ),
          )}
          {c ? <RoleLink to="/it" name={c.clinic.it_contact_name} sub="IT support · laptop or phone" role="it" /> : null}
          <Link className="btn btn-soft btn-block" to="/mission">Mission control (projector)</Link>
          <Link className="btn btn-soft btn-block" to="/backstage">Backstage (demo controls)</Link>
        </nav>

        <section className="card tight">
          <span className="section-label">Open on another phone</span>
          <p className="small">Join the same Wi-Fi or hotspot as this laptop, then open:</p>
          <p className="mono" style={{ fontSize: 16, wordBreak: "break-all" }}>{window.location.origin}</p>
        </section>

        <details className="log">
          <summary>All screens (for reviewers)</summary>
          <div className="body small">
            {people.filter((p) => p.role !== "owner").slice(0, 1).map((p) => (
              <span key={p.id} className="stack-sm" style={{ gap: 6 }}>
                <Link to={`/staff/${p.id}`}>Staff · Today and the alert card (after Backstage → password attack)</Link>
                <Link to={`/staff/${p.id}/drill`}>Staff · Join a drill, lobby, moments and results</Link>
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
