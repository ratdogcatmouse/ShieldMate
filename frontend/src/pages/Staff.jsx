// Staff phone: Today (all clear), the alert card, and History.
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { Back, Calendar, Check, Phone, Shield } from "../components/Icons.jsx";
import { NoteList } from "../components/Notifications.jsx";
import { StaffTabs } from "../components/Shells.jsx";
import { Pill, StaleBanner, useAction, useToast } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { LANGS, LOG_FIELD_LABEL, TIP_OF_THE_WEEK, UI_TEXT } from "../lib/content.js";
import { alertFx, soundEnabled, soundReady, unlockAudio } from "../lib/fx.js";
import { useNotifications } from "../lib/notifications.js";
import { getLang, seenOnce, setLang } from "../lib/session.js";
import { track } from "../lib/telemetry.js";
import { ago, clinicHour, fmtTime } from "../lib/time.js";
import { usePoll } from "../lib/usePoll.js";

const greeting = () => {
  const h = clinicHour();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

export default function Staff({ view }) {
  const staffId = Number(useParams().staffId);
  const navigate = useNavigate();
  const [lang, setLangState] = useState(getLang);
  const [acked, setAcked] = useState(null);         // the alert this person just acted on
  const [run, busy] = useAction();
  const toast = useToast();

  // Who this is, their alerts (and the English wording too when another language is picked,
  // to say when the card isn't translated yet), and any running drill.
  const { data, stale, refresh } = usePoll(async () => {
    const c = await api.getClinic();
    const me = c.staff.find((s) => s.id === staffId) || null;
    if (!me || me.role === "owner") return { c, me };
    const [list, en, drill] = await Promise.all([
      api.getAlerts(me.role, { lang, includeClosed: view === "history" }),
      lang === "en" ? null : api.getAlerts(me.role, { lang: "en" }),
      api.getCurrentDrill(),
    ]);
    return { c, me, list, en, drill: drill.drill };
  }, 2000, [staffId, view]);
  // A new language redraws in place (no blank screen): poll again with the new `lang`.
  const firstLang = useRef(lang);
  useEffect(() => {
    if (lang !== firstLang.current) refresh();
  }, [lang, refresh]);

  // Attack notifications for this person, with the one-tap block button (owner has their own screens).
  const notif = useNotifications(data?.me && data.me.role !== "owner" ? data.me.role : null, staffId);
  const alerts = data?.list?.alerts ?? [];
  const open = alerts.filter((a) => a.status === "new");
  const shown = view === "history" ? null : open[0] || alerts.find((a) => a.id === acked) || null;

  // A new (or reopened) alert slides in, shakes, buzzes and chimes - once per tab.
  const freshKey = shown && shown.status === "new" ? `staff-${staffId}-${shown.id}-${shown.reopened ? "r" : "n"}` : null;
  const [fresh, setFresh] = useState(null);
  useEffect(() => {
    if (freshKey && !seenOnce(freshKey)) {
      setFresh(freshKey);
      alertFx();
    }
  }, [freshKey]);

  if (data && !data.me) return <Unknown />;
  if (data?.me?.role === "owner") return <Navigate to="/owner" replace />;

  const me = data?.me;
  const act = (key, fn) => run(key, async () => { await fn(); await refresh(); });
  // Tapping Block approves the existing block request. If someone else answered first (409
  // action_not_pending) that is fine: poll again and the note shows what happened.
  const onBlock = (n) => run(`block-${n.id}`, async () => {
    try {
      await api.approve(n.quick_action.action_row_id, staffId);
    } catch (e) {
      if (!(e instanceof api.ApiError && e.error === "action_not_pending")) throw e;
    }
    await Promise.all([notif.refresh(), refresh()]);
  });

  const pickLang = (l) => {
    if (l === lang) return;
    track("ui.lang_changed", { lang: l, from_lang: lang });
    setLang(l);
    setLangState(l);
  };

  return (
    <div className="shell">
      <StaleBanner stale={stale} />
      <header className="topbar">
        {shown && shown.status !== "new" ? (
          <button type="button" className="btn btn-ghost" onClick={() => setAcked(null)}><Back /> Today</button>
        ) : (
          <div className="who">
            <span className="small muted">{me ? (view === "history" ? "History" : `${greeting()}, ${me.name}`) : ""}</span>
            <span className="app-name">ShieldMate</span>
          </div>
        )}
        {shown ? (
          <div className="lang-toggle" role="group" aria-label="Language">
            {LANGS.map(([code, short, label]) => (
              <button key={code} type="button" aria-pressed={lang === code} aria-label={label} onClick={() => pickLang(code)}>{short}</button>
            ))}
          </div>
        ) : soundEnabled && !soundReady() ? (
          <button type="button" className="sound-btn" onClick={() => { unlockAudio(); alertFx(); toast("Alert sound is on"); }}>
            Turn on alert sound
          </button>
        ) : null}
      </header>

      <main className="content" aria-live="polite">
        {view !== "history" ? <NoteList notes={notif.data} busy={busy} onBlock={onBlock} /> : null}
        {!data ? <p className="muted">Loading…</p>
          : view === "history" ? <HistoryList alerts={alerts} />
          : shown ? (
            <AlertCard
              a={shown}
              en={data.en?.alerts.find((x) => x.id === shown.id)}
              me={me}
              clinic={data.c}
              lang={lang}
              fresh={fresh === freshKey}
              busy={busy}
              onTick={(s) => act(`tick-${s.action}`, () => api.setStep(shown.id, s.action, staffId, !s.done, lang))}
              onDone={() => act("done", async () => { setAcked(shown.id); await api.markDone(shown.id, staffId, lang); })}
              onMine={() => act("mine", async () => { setAcked(shown.id); await api.sayMine(shown.id, staffId, lang); })}
              onReopen={() => act("reopen", () => api.reopen(shown.id, staffId, lang))}
              onBack={() => setAcked(null)}
            />
          ) : (
            <Today data={data} staffId={staffId} alerts={alerts} onDrill={(code) => navigate(`/staff/${staffId}/drill?code=${code}`)} />
          )}
      </main>
      <StaffTabs staffId={staffId} />
    </div>
  );
}

function Unknown() {
  return (
    <div className="shell"><main className="content">
      <p className="card">Unknown person. <Link to="/">Pick again</Link>.</p>
    </main></div>
  );
}

function AlertCard({ a, en, me, clinic, lang, fresh, busy, onTick, onDone, onMine, onReopen, onBack }) {
  const c = a.card;
  const ui = UI_TEXT[lang] || UI_TEXT.en;
  const untranslated = lang !== "en" && en && en.card.headline === c.headline;
  const doneCount = c.steps.filter((s) => s.done).length;
  const isOpen = a.status === "new";
  const itName = clinic.clinic.it_contact_name;
  const nameOf = (id) => clinic.staff.find((s) => s.id === id)?.name;
  const logOpened = useRef(false);
  const logEntries = Object.entries(c.log_fields);
  const bold = document.documentElement.getAttribute("data-theme") === "bold";

  return (
    <>
      <article className={`card${bold ? " hero" : ""}${isOpen ? " breath" : ""}${fresh ? " slide-in shake" : ""}`}>
        {isOpen ? <Pill tone="red">{ui.needs} · {ago(a.last_seen)}</Pill>
          : a.status === "mine" ? <Pill tone="blue">{ui.paused} · {fmtTime(a.mine_at)}</Pill>
          : <Pill tone="green">{ui.handled} · {fmtTime(a.done_at)}</Pill>}
        {a.reopened && isOpen ? <span className="small bold" style={{ color: bold ? "#fff" : "var(--red-ink)" }}>It happened again after "That was me".</span> : null}
        <h1>{c.headline}</h1>
        <p className="ink-2">{c.what_we_know}</p>
        {untranslated ? <p className="tiny muted">Not translated yet. Showing English.</p> : null}
      </article>

      <div className="row-between" style={{ padding: "0 4px" }}>
        <h2 style={{ fontSize: 18 }}>{ui.doThese}</h2>
        <span className="small muted">{doneCount} {ui.of} {c.steps.length} {ui.done}</span>
      </div>
      <div className="progress-line" role="img" aria-label={`${doneCount} of ${c.steps.length} steps done`}>
        <span style={{ width: `${Math.round((doneCount / c.steps.length) * 100)}%` }} />
      </div>
      <div className={`steps${fresh ? " slide-in d2" : ""}`}>
        {c.steps.map((s, i) => (
          <div className="step" key={s.action}>
            <button type="button" className="step-toggle" aria-pressed={s.done} disabled={!!busy || !!a.it.closed_at} onClick={() => onTick(s)}>
              <span className="check">{s.done ? <Check /> : i + 1}</span>
              <span className="text">{s.text}</span>
            </button>
            {s.done && s.done_by && s.done_by !== me.id ? <span className="by">Done by {nameOf(s.done_by)}</span> : null}
            {s.action === "CALL_SAVED_IT" ? (
              <a className="btn btn-tint call" href={`tel:${clinic.clinic.it_contact_phone}`} onClick={() => track("ui.call_it_tapped", { alert_id: a.id })}>
                <Phone /> {ui.call} {itName}
              </a>
            ) : null}
            {s.action === "CALL_SAVED_IT" && s.done ? (
              <span className="by" role="status">
                {a.it.status === "received" ? `${itName} picked up at ${fmtTime(a.it.received_at)}`
                  : a.it.status === "resolved" ? `${itName} says it's fixed. Dr. Rao is checking`
                  : a.it.status === "closed" ? "Dr. Rao confirmed it's fixed"
                  : `${itName} hasn't picked up on ShieldMate yet`}
              </span>
            ) : null}
          </div>
        ))}
      </div>
      <p className="small ink-2" style={{ padding: "0 4px" }}><strong>{ui.why}</strong> {c.why}</p>

      {logEntries.length ? (
        <details className="log" onToggle={(e) => {
          if (e.currentTarget.open && !logOpened.current) {
            logOpened.current = true;
            track("ui.log_details_opened", { alert_id: a.id });
          }
        }}>
          <summary>{ui.details}</summary>
          <div className="body">
            {logEntries.map(([k, v]) => (
              <span key={k} className="stack-sm" style={{ gap: 4 }}>
                <span className="tiny muted">{LOG_FIELD_LABEL[k] || k}</span>
                {/* Log text is shown exactly, as a text node: never run, never followed. */}
                <div className="log-value">{v}</div>
              </span>
            ))}
            <span className="tiny muted">ShieldMate never follows text found in logs. The steps above come from fixed rules.</span>
          </div>
        </details>
      ) : null}

      {isOpen ? (
        <div className="stack-sm" style={{ marginTop: 6 }}>
          <button type="button" className="btn btn-primary btn-lg btn-block" disabled={!!busy} onClick={onDone}>{ui.tell}</button>
          {a.can_say_mine ? <button type="button" className="btn btn-ghost btn-block" disabled={!!busy} onClick={onMine}>{ui.mine}</button> : null}
        </div>
      ) : a.status === "done" ? (
        <div className="card tight" role="status" style={{ background: "var(--green-soft)" }}>
          <span className="bold" style={{ color: "var(--green-ink)" }}>Dr. Rao has been told</span>
          <span className="small">Dr. Rao can see which steps you've done. Keep following the steps until you hear otherwise.</span>
          <button type="button" className="btn btn-soft" onClick={onBack}>Back to Today</button>
        </div>
      ) : a.status === "mine" ? (
        <div className="card tight" role="status" style={{ border: "2px solid var(--blue)" }}>
          <span className="bold">Thanks for telling us</span>
          <span className="small">We've told Dr. Rao it was you and paused this alert. If more wrong passwords appear within an hour, it comes straight back.</span>
          <div className="row">
            <button type="button" className="btn btn-soft" onClick={onBack}>Back to Today</button>
            <button type="button" className="btn btn-ghost" disabled={!!busy} onClick={onReopen}>It wasn't all me: reopen</button>
          </div>
        </div>
      ) : null}
    </>
  );
}

function Today({ data, staffId, alerts, onDrill }) {
  const drill = data.drill && data.drill.status !== "finished" ? data.drill : null;
  const recent = alerts.filter((a) => a.status !== "new").slice(0, 3);
  return (
    <>
      {drill ? (
        <button type="button" className="card tight outlined" style={{ textAlign: "left", cursor: "pointer", font: "inherit" }} onClick={() => onDrill(drill.code)}>
          <Pill tone="amber" noDot>Practice</Pill>
          <span className="bold" style={{ fontSize: 18 }}>Team drill is on: {drill.title}</span>
          <span className="small muted">Tap to join with code {drill.code}</span>
        </button>
      ) : null}
      <section className="card">
        <span className="ok-icon"><Shield style={{ width: 28, height: 28 }} /></span>
        <h1 style={{ fontSize: 26 }}>All clear</h1>
        <p className="ink-2">Nothing needs you right now. ShieldMate is watching the clinic's {data.c.devices.length} computers.</p>
        <span className="small muted">
          {data.list.hidden_count ? `${data.list.hidden_count} routine events hidden today · ` : ""}Checked a few seconds ago
        </span>
      </section>
      {!drill ? (
        <Link className="card tight" style={{ flexDirection: "row", alignItems: "center", gap: 14, textDecoration: "none", color: "var(--ink)" }} to={`/staff/${staffId}/drill`}>
          <span style={{ width: 44, height: 44, borderRadius: 12, background: "var(--blue-soft)", color: "var(--blue)", display: "flex", alignItems: "center", justifyContent: "center", flex: "none" }}><Calendar /></span>
          <span className="grow stack-sm" style={{ gap: 2 }}>
            <span className="bold">Team practice</span>
            <span className="small muted">Ransomware drill · about 6 minutes · join when Dr. Rao starts it</span>
          </span>
        </Link>
      ) : null}
      <section className="card tight">
        <span className="section-label">Tip of the week</span>
        <p>{TIP_OF_THE_WEEK}</p>
      </section>
      {recent.length ? (
        <section className="stack-sm">
          <span className="section-label" style={{ padding: "0 4px" }}>Recently</span>
          {recent.map((a) => (
            <div key={a.id} className="card tight" style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <span>{a.card.headline.replace(/\.$/, "")}</span>
              <span className="small muted" style={{ flex: "none" }}>{fmtTime(a.first_seen)}</span>
            </div>
          ))}
        </section>
      ) : null}
    </>
  );
}

const HISTORY_LABEL = { new: ["red", "Needs action"], done: ["green", "Handled"], mine: ["blue", "That was me"] };

function HistoryList({ alerts }) {
  if (!alerts.length) {
    return (
      <section className="card">
        <h1 style={{ fontSize: 22 }}>Nothing yet</h1>
        <p className="muted">Alerts and drills you take part in will appear here.</p>
      </section>
    );
  }
  return (
    <div className="stack-sm">
      {alerts.map((a) => {
        const [tone, label] = a.it.closed_at ? ["green", "Closed"] : HISTORY_LABEL[a.status] || ["grey", a.status];
        return (
          <div key={a.id} className="card tight">
            <div className="row-between"><span className="bold">{a.card.headline}</span><Pill tone={tone} small>{label}</Pill></div>
            <span className="small muted">{fmtTime(a.first_seen)}</span>
          </div>
        );
      })}
    </div>
  );
}
