// Staff phone: join a drill, wait in the lobby, answer each moment, see results.
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ImpactPills, Options, PhaseRows, Ring, Segments, playerTotal } from "../components/Drill.jsx";
import { sceneFor } from "../components/Scenes.jsx";
import { StaffTabs } from "../components/Shells.jsx";
import { Retest, StaleBanner, useAction, useToast } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { ACTION_LABEL, PHASE_LABEL, PREVIOUS_DRILL, ROLE_LABEL } from "../lib/content.js";
import { getPlayer, setPlayer } from "../lib/session.js";
import { track } from "../lib/telemetry.js";
import { useBodyClass } from "../lib/useBodyClass.js";
import { usePoll } from "../lib/usePoll.js";

export default function StaffDrill() {
  const staffId = Number(useParams().staffId);
  const [params] = useSearchParams();
  const code = params.get("code");
  const navigate = useNavigate();
  const toast = useToast();
  const [run, busy] = useAction();
  const [typed, setTyped] = useState(null);

  const { data, stale, refresh } = usePoll(async () => {
    const c = await api.getClinic();
    const me = c.staff.find((s) => s.id === staffId) || null;
    const playerId = code ? getPlayer(code, staffId) : null;
    if (!code || !playerId) return { c, me, current: (await api.getCurrentDrill()).drill };
    try {
      return { c, me, view: await api.getDrill(code, playerId) };
    } catch (e) {
      // The drill is gone (e.g. Backstage reset): back to the join screen.
      if (e.status === 404) return { c, me, gone: true, current: (await api.getCurrentDrill()).drill };
      throw e;  // a Wi-Fi blip: keep the screen, try again on the next poll
    }
  }, 2000, [staffId, code]);

  const view = data?.view;
  useBodyClass(view && view.status !== "lobby" ? "game-mode" : null);
  // What the code box shows: what was typed, else the code in the address (unless that drill
  // is gone), else the drill running now.
  const joinValue = typed ?? (data?.gone ? null : code) ?? data?.current?.code ?? "";

  const join = (e) => {
    e.preventDefault();
    const c = joinValue.replace(/\D/g, "");
    if (c.length !== 4) return toast("The code has 4 digits.");
    track("ui.drill_join_submitted", { code: c });
    run("join", async () => {
      const r = await api.joinDrill(c, staffId);
      setPlayer(c, staffId, r.player_id);
      setTyped(null);
      navigate(`/staff/${staffId}/drill?code=${c}`, { replace: true });
    });
  };
  const answer = (optionId) =>
    run("answer", async () => { await api.answer(code, view.me.player_id, view.step.step_id, optionId); await refresh(); });

  const banner = view?.status === "finished" ? "PRACTICE · finished" : "PRACTICE · not a real attack";
  const me = data?.me;
  return (
    <div className="shell">
      <div className="practice-banner" role="note">{banner}</div>
      <StaleBanner stale={stale} />
      <main className="content" id="main" aria-live="polite">
        {!data ? <p className="muted">Loading…</p>
          : !me ? <p className="card">Unknown person. <Link to="/">Pick again</Link>.</p>
          : !view ? (
            <JoinForm me={me} value={joinValue}
              current={data.current} onType={(v) => setTyped(v.replace(/\D/g, "").slice(0, 4))} onSubmit={join} busy={busy} />
          )
          : view.status === "lobby" ? <Lobby v={view} />
          : view.status === "finished" ? <Results v={view} staffId={staffId} />
          : <Moment v={view} onAnswer={answer} busy={busy} />}
      </main>
      <StaffTabs staffId={staffId} />
    </div>
  );
}

function JoinForm({ me, value, current, onType, onSubmit, busy }) {
  return (
    <>
      <div className="stack-sm">
        <h1 style={{ fontSize: 26 }}>Join the team drill</h1>
        <p className="ink-2">Type the 4-digit code shown on Dr. Rao's screen.</p>
      </div>
      <form className="stack-sm" noValidate onSubmit={onSubmit}>
        <label className="field-label" htmlFor="code">Drill code</label>
        <input id="code" className="code-input" inputMode="numeric" pattern="[0-9]*" maxLength={4} autoComplete="off"
          value={value} onChange={(e) => onType(e.target.value)} />
        <button className="btn btn-primary btn-lg btn-block" type="submit" disabled={!!busy}>Join as {me.name}</button>
      </form>
      <p className="small muted">
        {current ? `A drill is running now: ${current.title}` : "No drill is running yet. Dr. Rao starts one from the laptop."}
      </p>
      <Link className="btn btn-ghost" to="/">Not {me.name}? Switch person</Link>
    </>
  );
}

function Lobby({ v }) {
  return (
    <>
      <div className="stack-sm">
        <span className="small bold" style={{ color: "var(--green-ink)" }}>You're in · code {v.code}</span>
        <h1 style={{ fontSize: 26 }}>{v.title}</h1>
        <p className="ink-2">Waiting for Dr. Rao to start. Keep this screen open.</p>
      </div>
      <section className="list" aria-label="Who has joined">
        {v.team.players.map((p) => {
          const isMe = p.player_id === v.me.player_id;
          return (
            <div key={p.player_id} className="list-row">
              <span className={isMe ? "bold" : undefined}>
                {p.name} · {p.role === "owner" ? "host" : ROLE_LABEL[p.role].toLowerCase()}{isMe ? " (you)" : ""}
              </span>
              <span className="small bold" style={{ color: "var(--green-ink)" }}>Ready</span>
            </div>
          );
        })}
      </section>
      <section className="card tight">
        <span className="section-label">What to expect</span>
        <ul style={{ margin: 0, paddingLeft: 20 }} className="stack-sm">
          <li>{v.step_count} moments in one day at the clinic</li>
          <li>Pick what you would do; you'll see why straight away</li>
          <li>No timer. Nobody else sees your answer until everyone has chosen</li>
        </ul>
      </section>
    </>
  );
}

function TeamChips({ v }) {
  const verdict = Object.fromEntries((v.review?.answers || []).map((a) => [a.name, a.correct]));
  return (
    <div className="chips">
      <span className="small muted">Team</span>
      {v.team.players.filter((p) => p.has_options).map((p) => {
        const cls = !p.answered ? "wait" : verdict[p.name] === true ? "ok" : verdict[p.name] === false ? "no" : "done";
        const isMe = p.player_id === v.me.player_id;
        return (
          <span key={p.player_id} className="chip">
            <span className={`av ${cls}`}>{p.name.replace("Dr. ", "").charAt(0)}</span>
            {isMe ? "you" : p.name}{p.answered ? "" : " …"}
          </span>
        );
      })}
    </div>
  );
}

function Moment({ v, onAnswer, busy }) {
  const st = v.step;
  return (
    <>
      <div className="game-top">
        <div className="row-between">
          <span className="game-badge">MOMENT {v.step_index + 1} / {v.step_count}</span>
          <span>Team <strong style={{ color: "#fff", fontSize: 18 }}>{v.team.answered} / {v.team.total}</strong> answered</span>
        </div>
        <Segments index={v.step_index} count={v.step_count} />
        <span>{st.game_time} at the clinic · {PHASE_LABEL[st.phase]}</span>
      </div>
      {sceneFor(v.scenario_id, st.step_id)}
      <div className="game-sheet">
        <p style={{ fontSize: 19, fontWeight: 700, lineHeight: 1.4 }}>{st.situation}</p>
        <ImpactPills impact={v.impact} />
        {!v.options.length ? (
          <section className="verdict">
            <span className="bold">Dr. Rao is deciding this one</span>
            <span className="fb">It's the owner's call. Watch the big screen; you'll see the answer when everyone has chosen.</span>
          </section>
        ) : (
          <>
            <Options view={v} onAnswer={onAnswer} disabled={!!busy} />
            {v.my_answer ? (
              <section className="verdict slide-in" role="status">
                <span className="bold" style={{ fontSize: 18 }}>{v.my_answer.correct ? "Nice call! +1 for the team" : "Close, but not quite."}</span>
                <span className="fb">{v.my_answer.feedback}</span>
              </section>
            ) : v.status === "review" ? (
              <section className="verdict"><span className="bold">This moment closed before you answered.</span></section>
            ) : null}
          </>
        )}
        <TeamChips v={v} />
        <span className="small muted">
          {v.status === "review" ? "Everyone has chosen · Dr. Rao moves you on"
            : `${v.team.answered} of ${v.team.total} answered · no timer, take your time`}
        </span>
      </div>
    </>
  );
}

function Results({ v, staffId }) {
  const r = v.results;
  const mine = r.players.find((p) => p.name === v.me.name);
  if (!mine) {
    return <div className="game-sheet"><h1>Drill finished</h1><Link className="btn btn-dark btn-lg btn-block" to={`/staff/${staffId}`}>Back to Today</Link></div>;
  }
  const t = playerTotal(mine);
  const prev = PREVIOUS_DRILL.scenario_id === v.scenario_id ? PREVIOUS_DRILL : null;
  const better = prev ? r.team.correct - prev.team_right : 0;
  return (
    <>
      <div className="game-top" style={{ alignItems: "center", textAlign: "center", paddingBottom: 18 }}>
        <Ring right={t.correct} total={t.total} label={`You got ${t.correct} of ${t.total}`} />
        <span style={{ fontFamily: "var(--display)", fontSize: 26, fontWeight: 700 }}>
          {prev && better > 0 ? "Your team got better" : t.correct === t.total ? "Every call right" : "Practice done"}
        </span>
        <span style={{ color: "var(--game-ink)" }}>
          {prev && better > 0 ? `${better} more right calls than ${prev.label.toLowerCase()}` : `Team ${r.team.correct} of ${r.team.total}`}
        </span>
      </div>
      <div className="game-sheet">
        {prev ? <section className="card tight"><Retest prev={prev} right={r.team.correct} total={r.team.total} /></section> : null}
        <PhaseRows results={r} player={mine} />
        {mine.missed_actions.length ? (
          <section className="verdict">
            <span className="section-label" style={{ color: "var(--game-ink)" }}>Remember these</span>
            {mine.missed_actions.map((a, i) => <span key={a} className="bold" style={{ fontSize: 18 }}>{i + 1}. {ACTION_LABEL[a] || a}</span>)}
          </section>
        ) : null}
        <Link className="btn btn-dark btn-lg btn-block" to={`/staff/${staffId}`}>Back to Today</Link>
      </div>
    </>
  );
}
