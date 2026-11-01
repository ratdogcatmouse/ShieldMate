// Staff phone: join a drill, wait in the lobby, answer each step, read the debrief.
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ImpactPills, Options, PhaseRows, Segments, playerTotal } from "../components/Drill.jsx";
import { sceneFor } from "../components/Scenes.jsx";
import { StaffTabs } from "../components/Shells.jsx";
import { Rephrasable, RephraseProvider } from "../components/Rephrase.jsx";
import { Retest, StaleBanner, useAction, useToast } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { ACTION_LABEL, PHASE_LABEL, PREVIOUS_DRILL, ROLE_LABEL } from "../lib/content.js";
import { getPlayer, setPlayer } from "../lib/session.js";
import { track } from "../lib/telemetry.js";
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

  const banner = view?.status === "finished" ? "Practice drill · finished" : "Practice drill · This is not a real alert";
  const me = data?.me;
  return (
    <RephraseProvider role={me?.role} lang="en" drillCode={view?.code}>
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
    </RephraseProvider>
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
          <li>{v.step_count} steps through one day at the clinic</li>
          <li>Choose what you would do. The reason is shown after you answer</li>
          <li>There is no timer. Nobody sees your answer until everyone has chosen</li>
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
      <section className="card tight drill-head" aria-label="Drill progress">
        <div className="row-between">
          <span className="bold">{v.title}</span>
          <span className="small muted">Team <strong style={{ color: "var(--ink)" }}>{v.team.answered} / {v.team.total}</strong> answered</span>
        </div>
        <Segments index={v.step_index} count={v.step_count} />
        <span className="meta">Step {v.step_index + 1} of {v.step_count} · {st.game_time} at the clinic · {PHASE_LABEL[st.phase]}</span>
      </section>
      {sceneFor(v.scenario_id, st.step_id)}
      <Rephrasable id={`moment-${st.step_id}`} kind="This step" title={`Step ${v.step_index + 1}`} text={st.situation}>
        <p className="situation">{st.situation}</p>
      </Rephrasable>
      <ImpactPills impact={v.impact} />
      {!v.options.length ? (
        <section className="verdict">
          <span className="head">Dr. Rao decides this step</span>
          <span className="fb">This decision belongs to the owner. The answer is shown on the main screen once everyone has chosen.</span>
        </section>
      ) : (
        <>
          <Options view={v} onAnswer={onAnswer} disabled={!!busy} />
          {v.my_answer ? (
            <Rephrasable id={`why-${st.step_id}`} kind="Why" title={v.my_answer.correct ? "Correct" : "Not the recommended action"} text={v.my_answer.feedback}>
              <section className={`verdict ${v.my_answer.correct ? "ok" : "no"} slide-in`} role="status">
                <span className="head">{v.my_answer.correct ? "Correct" : "Not the recommended action"}</span>
                <span className="fb">{v.my_answer.feedback}</span>
              </section>
            </Rephrasable>
          ) : v.status === "review" ? (
            <section className="verdict"><span className="head">This step closed before you answered.</span></section>
          ) : null}
        </>
      )}
      <TeamChips v={v} />
      <span className="small muted">
        {v.status === "review" ? "Everyone has chosen · Dr. Rao moves the team on"
          : `${v.team.answered} of ${v.team.total} answered · no time limit`}
      </span>
    </>
  );
}

function Results({ v, staffId }) {
  const r = v.results;
  const mine = r.players.find((p) => p.name === v.me.name);
  if (!mine) {
    return (
      <section className="card">
        <h1>Drill complete</h1>
        <Link className="btn btn-primary btn-lg btn-block" to={`/staff/${staffId}`}>Back to Today</Link>
      </section>
    );
  }
  const t = playerTotal(mine);
  const prev = PREVIOUS_DRILL.scenario_id === v.scenario_id ? PREVIOUS_DRILL : null;
  const better = prev ? r.team.correct - prev.team_right : 0;
  return (
    <>
      <section className="card debrief-head" aria-label="Drill summary">
        <span className="section-label">Debrief · {v.title}</span>
        <h1>{t.correct === t.total ? "All actions correct" : "Drill complete"}</h1>
        <div className="facts">
          <div className="fact"><span className="k">Your actions</span><span className="v num">{t.correct} / {t.total}</span></div>
          <div className="fact"><span className="k">Team</span><span className="v num">{r.team.correct} / {r.team.total}</span></div>
        </div>
        {prev && better > 0 ? <span className="small ink-2">Team improved by {better} correct action{better === 1 ? "" : "s"} since {prev.label.toLowerCase()}.</span> : null}
      </section>
      {prev ? <section className="card tight"><Retest prev={prev} right={r.team.correct} total={r.team.total} /></section> : null}
      <PhaseRows results={r} player={mine} />
      {mine.missed_actions.length ? (
        <section className="card tight">
          <span className="section-label">Actions to review</span>
          <ol className="playbook">
            {mine.missed_actions.map((a) => <li key={a} className="bold">{ACTION_LABEL[a] || a}</li>)}
          </ol>
        </section>
      ) : null}
      <Link className="btn btn-primary btn-lg btn-block" to={`/staff/${staffId}`}>Back to Today</Link>
    </>
  );
}
