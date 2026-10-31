import { useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { getAlerts, getClinic, getNotifications, joinDrill, markDone } from "../api.js";
import { usePoll } from "../usePoll.js";
import { clearNotifSince, getLang, getNotifSince, setDrill, setLang, setNotifSince } from "../session.js";
import { track } from "../telemetry.js";
import { fmtTime } from "../format.js";
import { Icon } from "../icons.jsx";
import AlertCard from "../components/AlertCard.jsx";
import { ErrorBanner, StaleBanner } from "../components/Badge.jsx";
import { Topbar } from "../components/Shells.jsx";

const LANGS = [["en", "EN", "English"], ["kn", "ಕ", "Kannada"], ["hi", "हि", "Hindi"]];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function Staff() {
  const { staffId } = useParams();
  const navigate = useNavigate();
  const [lang, setLangState] = useState(getLang);
  const [handledIds, setHandledIds] = useState([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [code, setCode] = useState("");

  const clinic = usePoll(getClinic, 30000);
  const person = clinic.data?.staff.find((s) => String(s.id) === staffId);
  const role = person?.role;

  const alerts = usePoll(role ? () => getAlerts(role, lang) : null, 2000, [role, lang]);
  usePoll(
    role
      ? async () => {
          const res = await getNotifications(role, person.id, getNotifSince());
          // Reset makes the server count from 1 again: clear the cursor when last_id drops.
          if (res.last_id < getNotifSince()) clearNotifSince();
          else if (res.last_id > 0) setNotifSince(res.last_id);
          return res;
        }
      : null,
    2000,
    [role],
  );

  // /staff/99 or a stale link: the clinic loaded and has no such person, so go back to the picker.
  if (clinic.data && !person) return <Navigate to="/" replace />;

  // Alert ids start from 1 again after a Backstage reset, so "handled" is remembered by id and first_seen.
  const handledKey = (a) => `${a.id}@${a.first_seen}`;
  const isHandled = (a) => handledIds.includes(handledKey(a));
  const list = alerts.data?.alerts || [];
  const open = list.find((a) => a.status === "new" && !isHandled(a));
  const shown = open || list.find(isHandled);
  const recent = list.filter((a) => a !== shown && a.status !== "new").slice(0, 3);

  const pickLang = (l) => {
    if (l !== lang) track("ui.lang_changed", { lang: l, from_lang: lang });
    setLang(l);
    setLangState(l);
  };

  const done = async (alert) => {
    setBusy(true);
    setActionError(null);
    try {
      await markDone(alert.id, person.id);
      setHandledIds((ids) => [...ids, handledKey(alert)]);
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  const join = async (e) => {
    e.preventDefault();
    setActionError(null);
    // Typed text: only a well-formed 4-digit code is worth logging.
    track("ui.drill_join_submitted", { code: /^\d{4}$/.test(code) ? code : null });
    try {
      const res = await joinDrill(code, person.id);
      setDrill({ code: res.code, player_id: res.player_id });
      navigate(`/drill/${res.code}`);
    } catch (err) {
      setActionError(err);
    }
  };

  const topLeft = (
    <div className="who" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span className="small muted">{person ? `${greeting()}, ${person.name}` : ""}</span>
      <span className="app-name">ShieldMate</span>
    </div>
  );
  const topRight = shown && (
    <div className="lang-toggle" role="group" aria-label="Language">
      {LANGS.map(([l, label, name]) => (
        <button key={l} type="button" aria-pressed={lang === l} aria-label={name} onClick={() => pickLang(l)}>
          {label}
        </button>
      ))}
    </div>
  );

  return (
    <>
      <Topbar left={topLeft} right={topRight} />
      <ErrorBanner error={actionError || alerts.error || clinic.error} />
      <StaleBanner stale={alerts.stale || clinic.stale} />
      <main className="content" aria-live="polite">
        {shown ? (
          <AlertCard
            alert={shown}
            it={clinic.data?.clinic}
            busy={busy}
            handled={isHandled(shown)}
            onDone={() => done(shown)}
          />
        ) : (
          person && alerts.data && (
            <>
              <section className="card">
                <span className="ok-icon"><Icon name="shield" size={28} /></span>
                <h1 style={{ fontSize: 26 }}>All clear</h1>
                <p className="ink-2">
                  Nothing needs you right now. ShieldMate is watching the clinic's {clinic.data.devices.length} computers.
                </p>
                <span className="small muted">
                  {alerts.data.hidden_count > 0 ? `${alerts.data.hidden_count} routine events hidden today` : "Checked a few seconds ago"}
                </span>
              </section>

              <form className="card tight" onSubmit={join}>
                <span className="section-label">Team practice</span>
                <span className="small muted">Ransomware drill · join when Dr. Rao starts it. Type the 4-digit code.</span>
                <input
                  className="code-input"
                  aria-label="Drill code"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={4}
                  autoComplete="off"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 4))}
                />
                <button className="btn btn-primary btn-block" type="submit" disabled={code.length !== 4}>
                  Join as {person.name}
                </button>
              </form>

              <section className="card tight">
                <span className="section-label">Tip of the week</span>
                <p>If a pop-up or note gives you a phone number for "IT support", don't call it. Only use the contact saved in ShieldMate.</p>
              </section>
            </>
          )
        )}

        {recent.length > 0 && (
          <section className="stack-sm">
            <span className="section-label" style={{ padding: "0 4px" }}>Recently</span>
            {recent.map((a) => (
              <div key={a.id} className="card tight" style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <span>{a.card.headline.replace(/\.$/, "")}</span>
                <span className="small muted" style={{ flex: "none" }}>{fmtTime(a.first_seen)}</span>
              </div>
            ))}
          </section>
        )}
      </main>
    </>
  );
}
