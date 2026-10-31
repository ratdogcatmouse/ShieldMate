import { Link, useNavigate } from "react-router-dom";
import { API_MODE, getClinic } from "../api.js";
import { usePoll } from "../usePoll.js";
import { setStaff } from "../session.js";
import { ROLE_LABEL } from "../format.js";
import { Icon } from "../icons.jsx";
import QrCode from "../components/QrCode.jsx";
import { ErrorBanner, StaleBanner } from "../components/Badge.jsx";
import { Topbar } from "../components/Shells.jsx";

export default function Start() {
  const navigate = useNavigate();
  const { data, error, stale } = usePoll(getClinic, 30000);
  const address = window.location.origin;

  const pick = (person) => {
    setStaff({ id: person.id, name: person.name, role: person.role });
    navigate(person.role === "owner" ? "/owner" : `/staff/${person.id}`);
  };

  return (
    <>
      <Topbar right={<span className="pill pill-sim" style={{ color: "var(--night-muted)" }}>{API_MODE === "mock" ? "Demo data" : "Live server"}</span>} />
      <ErrorBanner error={!data && error} />
      <StaleBanner stale={stale} />
      <main className="content">
        <div className="stack-sm">
          <h1 style={{ fontSize: 26 }}>Who's using this device?</h1>
          <p className="muted">{data ? data.clinic.name : "ShieldMate"}. Pick once; this device remembers.</p>
        </div>

        <nav aria-label="Choose who you are" className="stack-sm">
          {data?.staff.map((person) => (
            <button key={person.id} type="button" className="role-link" onClick={() => pick(person)} style={{ font: "inherit", textAlign: "left", cursor: "pointer" }}>
              <span className="stack-sm" style={{ gap: 0 }}>
                <span className="bold">{person.name}</span>
                <span className="small muted">{ROLE_LABEL[person.role]} · {person.role === "owner" ? "laptop or phone" : "phone"}</span>
              </span>
              <span style={{ color: "var(--accent)" }}><Icon name="chevron" /></span>
            </button>
          ))}
          <Link className="btn btn-soft btn-block" to="/backstage">Backstage (demo controls)</Link>
        </nav>

        <section className="card tight">
          <span className="section-label">Open on another phone</span>
          <p className="small">Join the same Wi-Fi or hotspot as this laptop, then open:</p>
          <p className="mono" style={{ fontSize: 16, wordBreak: "break-all" }}>{address}</p>
          <QrCode value={address} />
        </section>
      </main>
    </>
  );
}
