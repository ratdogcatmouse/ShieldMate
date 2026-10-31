import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { advance, answer, getDrill, joinDrill, runRestore } from "../api.js";
import { usePoll } from "../usePoll.js";
import { clearDrill, getDrill as getStoredDrill, getStaff, setDrill } from "../session.js";
import { Icon } from "../icons.jsx";
import { ErrorBanner, PracticeBanner, StaleBanner } from "../components/Badge.jsx";
import ImpactMeter from "../components/ImpactMeter.jsx";
import QrCode from "../components/QrCode.jsx";
import RestoreResult from "../components/RestoreResult.jsx";
import TeamProgress from "../components/TeamProgress.jsx";
import { Topbar } from "../components/Shells.jsx";

const PHASE = { detect: "Detect", contain: "Contain", recover: "Recover", report: "Report" };
const ROLE = { front_desk: "front desk", billing: "billing", owner: "owner" };

function Lobby({ v, onBegin, busy }) {
  const host = v.me.is_host;
  return (
    <>
      <div className="stack-sm">
        <span className="small bold" style={{ color: "var(--green-text)" }}>You're in · code {v.code}</span>
        <h1 style={{ fontSize: 26 }}>{v.title}</h1>
        <p className="ink-2">{host ? "Wait for everyone to join, then begin." : "Waiting for Dr. Rao to start. Keep this screen open."}</p>
      </div>
      {host && (
        <section className="card tight">
          <span className="section-label">Others join with</span>
          <span className="mono" style={{ fontSize: 36, letterSpacing: "0.3em" }}>{v.code}</span>
          <QrCode value={window.location.href} size={120} />
        </section>
      )}
      <section className="list" aria-label="Who has joined">
        {v.team.players.map((p) => (
          <div className="list-row" key={p.player_id}>
            <span className={p.player_id === v.me.player_id ? "bold" : undefined}>
              {p.name} · {ROLE[p.role]}{p.player_id === v.me.player_id ? " (you)" : ""}
            </span>
            <span className="small bold" style={{ color: "var(--green-text)" }}>Ready</span>
          </div>
        ))}
      </section>
      <section className="card tight">
        <span className="section-label">What to expect</span>
        <ul className="stack-sm" style={{ margin: 0, paddingLeft: 20 }}>
          <li>{v.step_count} moments in one morning at the clinic</li>
          <li>Pick what you would do; you'll see why straight away</li>
          <li>No timer. Take your time</li>
        </ul>
      </section>
      {host && v.can_advance && (
        <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy} onClick={onBegin}>Begin</button>
      )}
    </>
  );
}

function Options({ v, onPick, busy }) {
  const mine = v.my_answer;
  return (
    <>
      <h2 style={{ fontSize: 18, padding: "0 4px" }}>What do you do?</h2>
      <div className="options" role="group" aria-label="Answers">
        {v.options.map((o, i) => {
          const letter = "ABCD"[i];
          if (!mine) {
            return (
              <button key={o.option_id} type="button" className="option" disabled={busy} onClick={() => onPick(o.option_id)}>
                <span className="mark">{letter}</span>
                <span>{o.text}</span>
              </button>
            );
          }
          if (mine.option_id === o.option_id) {
            // An icon and a word, not only colour.
            return (
              <div key={o.option_id} className={`option ${mine.correct ? "right" : "wrong"}`}>
                <span className="mark"><Icon name={mine.correct ? "check" : "cross"} /></span>
                <span>{o.text}<span className="tag">{mine.correct ? "Your answer · right" : "Your answer · not quite"}</span></span>
              </div>
            );
          }
          return (
            <div key={o.option_id} className="option dim"><span className="mark">{letter}</span><span>{o.text}</span></div>
          );
        })}
      </div>
      {mine && (
        <section className="card tight" role="status">
          <span className="bold">{mine.correct ? "Right." : "Not quite."}</span>
          <span>{mine.feedback}</span>
        </section>
      )}
    </>
  );
}

function Results({ v }) {
  const r = v.results;
  const me = r.players.find((p) => p.name === v.me.name);
  return (
    <>
      <div className="stack-sm">
        <span className="small muted">{v.title}{me ? ` · ${me.name}` : ""}</span>
        <h1 style={{ fontSize: 26 }}>Team result: {r.team.correct} of {r.team.total} right</h1>
      </div>
      <section className="list" aria-label="By person">
        {r.players.map((p) => {
          const right = Object.values(p.by_phase).reduce((n, s) => n + s.correct, 0);
          const total = Object.values(p.by_phase).reduce((n, s) => n + s.total, 0);
          return (
            <div className="list-row" key={p.name} style={{ alignItems: "flex-start" }}>
              <span className="stack-sm" style={{ gap: 2 }}>
                <span className={p.name === v.me.name ? "bold" : undefined}>{p.name}</span>
                <span className="small muted">
                  {r.phases.map((ph) => `${PHASE[ph]} ${p.by_phase[ph]?.correct ?? 0}/${p.by_phase[ph]?.total ?? 0}`).join(" · ")}
                </span>
              </span>
              <span className="bold">{right} of {total}</span>
            </div>
          );
        })}
      </section>
      {me && me.missed_actions.length > 0 && (
        <section className="card dark">
          <span className="section-label on-dark-muted">Remember these</span>
          {me.missed_actions.map((m, i) => (
            <span key={m} className="bold" style={{ fontSize: 18 }}>{i + 1}. {m.replace(/_/g, " ").toLowerCase()}</span>
          ))}
        </section>
      )}
      {r.restore && <p className="small muted">Backup test during the drill: {r.restore.result}</p>}
    </>
  );
}

export default function Drill() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [restore, setRestore] = useState(null);
  const stored = getStoredDrill();
  const playerId = stored?.code === code ? stored.player_id : null;

  // Join is idempotent per staff_id, so a device with no stored membership can simply join.
  useEffect(() => {
    if (playerId !== null) return;
    const me = getStaff();
    if (!me?.id) {
      navigate("/");
      return;
    }
    joinDrill(code, me.id)
      .then((res) => setDrill({ code, player_id: res.player_id }))
      .catch(setActionError);
  }, [code, playerId, navigate]);

  const { data: v, error, stale } = usePoll(
    playerId !== null ? () => getDrill(code, playerId) : null,
    2000,
    [code, playerId],
  );

  useEffect(() => {
    if (error?.error === "drill_not_found") clearDrill();
  }, [error]);
  useEffect(() => {
    if (v?.status === "finished") clearDrill();
  }, [v?.status]);

  const guard = async (fn) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  const phaseLabel = v?.step ? PHASE[v.step.phase] : null;
  return (
    <>
      <Topbar
        left={
          <Link className="btn btn-ghost" to="/" aria-label="Leave the drill">
            <Icon name="back" /> ShieldMate
          </Link>
        }
      />
      <PracticeBanner />
      <ErrorBanner error={actionError || error} />
      <StaleBanner stale={stale} />
      <main className="content" aria-live="polite">
        {!v && !error && <p className="muted">Joining drill {code}…</p>}
        {error?.error === "drill_not_found" && (
          <section className="card"><h1 style={{ fontSize: 22 }}>That drill isn't running</h1><Link to="/">Back to start</Link></section>
        )}
        {v?.status === "lobby" && (
          <Lobby v={v} busy={busy} onBegin={() => guard(() => advance(code, playerId))} />
        )}
        {v && (v.status === "open" || v.status === "review") && v.step && (
          <>
            <TeamProgress index={v.step_index} count={v.step_count} phase={phaseLabel} gameTime={v.step.game_time} />
            <article className="card">
              <p style={{ fontSize: 19, fontWeight: 700, lineHeight: 1.45 }}>{v.step.situation}</p>
            </article>
            <ImpactMeter impact={v.impact} />
            {v.options.length > 0 ? (
              <Options v={v} busy={busy} onPick={(optionId) => guard(() => answer(code, playerId, v.step.step_id, optionId))} />
            ) : (
              <section className="card tight">
                <span className="bold">{v.waiting_message || "Dr. Rao is deciding this one"}</span>
              </section>
            )}
            {v.status === "review" && v.review && (
              <section className="list" aria-label="What the team chose">
                {v.review.answers.map((a) => (
                  <div className="list-row" key={a.name} style={{ alignItems: "flex-start" }}>
                    <span className="stack-sm" style={{ gap: 0 }}>
                      <span className="bold">{a.name}</span>
                      <span className="small muted">{a.option_text ?? "No answer"}</span>
                    </span>
                    <span className="small bold" style={{ color: a.correct ? "var(--green-text)" : "var(--red-text)" }}>
                      {a.correct ? "✓ Right" : "✗ Not quite"}
                    </span>
                  </div>
                ))}
              </section>
            )}
            <div className="card tight" style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <span className="small">
                {v.status === "review"
                  ? "Everyone has chosen"
                  : `${v.team.answered} of ${v.team.total} answered · take your time`}
              </span>
              {v.can_advance && (
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => guard(() => advance(code, playerId))}>
                  {v.status === "review" && v.step_index + 1 >= v.step_count ? "Finish" : "Next"}
                </button>
              )}
            </div>
            {v.me.is_host && v.restore_check_available && (
              <button type="button" className="btn btn-soft btn-block" disabled={busy} onClick={() => guard(async () => setRestore(await runRestore()))}>
                Test the backup now
              </button>
            )}
            {restore && <RestoreResult run={restore} />}
          </>
        )}
        {v?.status === "finished" && v.results && (
          <>
            <Results v={v} />
            <Link className="btn btn-dark btn-lg btn-block" to="/">Back to start</Link>
          </>
        )}
      </main>
    </>
  );
}
