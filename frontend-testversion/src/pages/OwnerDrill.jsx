// Owner: start and host a team drill. Lobby with the join code, each step, the owner's own
// decisions, the restore check when the scenario calls for it, and the team's results.
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ImpactPills, Options, missedText, playerTotal } from "../components/Drill.jsx";
import { Rephrasable, RephraseProvider } from "../components/Rephrase.jsx";
import { OwnerShell } from "../components/Shells.jsx";
import { Pill, Retest, StatusPill, useAction } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { PHASE_LABEL, PREVIOUS_DRILL, ROLE_LABEL, SCENARIOS } from "../lib/content.js";
import { ownerOf } from "../lib/derive.js";
import { getPlayer, setLastDrill, setPlayer } from "../lib/session.js";
import { toMs } from "../lib/time.js";
import { usePoll } from "../lib/usePoll.js";

export default function OwnerDrill() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [run, busy] = useAction();
  const [scenario, setScenario] = useState(params.get("scenario") || SCENARIOS[0].id);
  const code = params.get("code");
  const sourceAlert = Number(params.get("alert")) || null;

  const { data, stale, refresh } = usePoll(async () => {
    const clinic = await api.getClinic();
    const owner = ownerOf(clinic);
    let c = code;
    if (!c) {
      // A drill already running (started on another screen) is picked up rather than duplicated.
      const cur = (await api.getCurrentDrill()).drill;
      if (!cur) return { clinic, owner };
      c = cur.code;
    }
    let pid = getPlayer(c, owner.id);
    try {
      if (!pid) {
        pid = (await api.joinDrill(c, owner.id)).player_id;   // the host's own player (rejoin = same id)
        setPlayer(c, owner.id, pid);
      }
      const [view, restore] = await Promise.all([api.getDrill(c, pid), api.getRestoreLatest()]);
      setLastDrill(c);                                        // Readiness shows this drill's results
      return { clinic, owner, code: c, view, restore };
    } catch (e) {
      // The drill is gone (e.g. Backstage reset) or finished before this screen joined it.
      if (e.status === 404 || e.error === "drill_finished") return { clinic, owner, gone: c };
      throw e;
    }
  }, 2000, [code]);

  // A running drill found without a code in the address: put its code there.
  useEffect(() => {
    if (data?.code && data.code !== code) navigate(`/owner/drill?code=${data.code}`, { replace: true });
  }, [data?.code, code, navigate]);

  const v = data?.view;
  const pid = v?.me.player_id;
  const act = (key, fn) => run(key, async () => { await fn(); await refresh(); });

  const start = () => run("start", async () => {
    const r = await api.createDrill(scenario, data.owner.id, sourceAlert);
    setPlayer(r.code, data.owner.id, r.player_id);
    setLastDrill(r.code);
    navigate(`/owner/drill?code=${r.code}`, { replace: true });
  });

  let body;
  if (!data) body = <p className="muted">Loading…</p>;
  else if (!v) body = <StartForm scenario={scenario} setScenario={setScenario} fromAlert={!!sourceAlert} busy={busy} onStart={start} gone={data.gone} />;
  else if (v.status === "lobby") body = <Lobby v={v} busy={busy} onAdvance={() => act("advance", () => api.advance(code, pid))} />;
  else if (v.status === "finished") body = <Results v={v} onNew={() => navigate("/owner/drill", { replace: true })} />;
  else {
    body = (
      <Moment v={v} restore={data.restore} busy={busy}
        onAnswer={(opt) => act("answer", () => api.answer(code, pid, v.step.step_id, opt))}
        onAdvance={() => act("advance", () => api.advance(code, pid))}
        onEnd={() => act("end", () => api.endDrill(code, pid))}
        onRestore={() => act("restore", async () => { await new Promise((r) => setTimeout(r, 1500)); await api.runRestore(); })} />
    );
  }
  return (
    <RephraseProvider role="owner" lang="en" drillCode={v?.code}>
      <OwnerShell clinicName={data?.clinic.clinic.name} ownerName={data?.owner?.name} stale={stale}>
        {body}
      </OwnerShell>
    </RephraseProvider>
  );
}

function StartForm({ scenario, setScenario, fromAlert, busy, onStart, gone }) {
  return (
    <>
      <div className="owner-head"><div><span className="owner-mobile-head">Team practice</span><h1>Team drill</h1></div></div>
      <div className="cols">
        <section className="card col-main">
          <h2>Practise with your team</h2>
          <p className="ink-2">A guided incident exercise on everyone's phone. No real systems are touched.</p>
          {gone ? <p className="small muted">Drill {gone} has ended. Start a new one below.</p> : null}
          <label className="field-label" htmlFor="scenario">Scenario</label>
          <select id="scenario" className="field" value={scenario} onChange={(e) => setScenario(e.target.value)}>
            {SCENARIOS.map((s) => <option key={s.id} value={s.id}>{s.title} (about {s.minutes} min)</option>)}
          </select>
          {fromAlert ? <p className="small muted">Suggested from today's alert.</p> : null}
          <button type="button" className="btn btn-primary btn-lg" style={{ alignSelf: "flex-start" }} disabled={!!busy} onClick={onStart}>
            Start team drill
          </button>
        </section>
        <aside className="col-side">
          <section className="card tight">
            <span className="section-label">How it works</span>
            <span className="small">1. Start, and a 4-digit code appears.<br />2. Staff open ShieldMate, tap Drills and type the code.<br />3. You move everyone through each step and discuss the answers.</span>
          </section>
        </aside>
      </div>
    </>
  );
}

function Lobby({ v, busy, onAdvance }) {
  const players = v.team.players;
  return (
    <>
      <div className="owner-head"><div><span className="small muted">{v.title}</span><h1>Waiting for the team</h1></div></div>
      <div className="cols">
        <div className="col-main">
          <section className="card">
            <span className="section-label">Join code</span>
            <span className="mono" style={{ fontSize: 56, letterSpacing: "0.12em", lineHeight: 1 }}>{v.code}</span>
            <span className="ink-2">On their phones: ShieldMate → Drills → type this code.</span>
          </section>
          <button type="button" className="btn btn-primary btn-lg" style={{ alignSelf: "flex-start" }} disabled={players.length < 2 || !!busy} onClick={onAdvance}>
            Begin step 1
          </button>
          {players.length < 2 ? <span className="small muted">Waiting for at least one person to join.</span> : null}
        </div>
        <aside className="col-side">
          <section className="list" aria-label="Joined">
            <h2 style={{ fontSize: 18, margin: "12px 0 4px" }}>{players.length} joined</h2>
            {players.map((p) => (
              <div key={p.player_id} className="list-row">
                <span>{p.name} · {p.role === "owner" ? "host" : ROLE_LABEL[p.role].toLowerCase()}</span>
                <StatusPill status="ok" label="Ready" />
              </div>
            ))}
          </section>
        </aside>
      </div>
    </>
  );
}

function Moment({ v, restore, busy, onAnswer, onAdvance, onEnd, onRestore }) {
  const st = v.step;
  const verdict = Object.fromEntries((v.review?.answers || []).map((a) => [a.name, a.correct]));
  // Only a check run during this step counts as the drill's restore check.
  const tested = restore && restore.result !== "NOT_TESTED" && st.opened_at && toMs(restore.started_at) >= toMs(st.opened_at) ? restore : null;
  const nextLabel = v.status === "open" ? "Close this step" : v.step_index < v.step_count - 1 ? "Next step" : "Finish drill";
  return (
    <>
      <div className="owner-head">
        <div>
          <span className="small muted">{v.title} · Step {v.step_index + 1} of {v.step_count} · {st.game_time} · {PHASE_LABEL[st.phase]}</span>
          <Rephrasable id={`moment-${st.step_id}`} kind="This step" title={`Step ${v.step_index + 1}`} text={st.situation}>
            <h1 style={{ fontSize: 24, lineHeight: 1.3 }}>{st.situation}</h1>
          </Rephrasable>
        </div>
        <Pill tone="amber" noDot>Practice · code <span className="mono">{v.code}</span></Pill>
      </div>
      <ImpactPills impact={v.impact} />
      <div className="cols">
        <div className="col-main">
          {v.options.length ? (
            <>
              <span className="section-label">Your answer (owner's decision)</span>
              <Options view={v} onAnswer={onAnswer} disabled={!!busy} letters="ABC" />
              {v.my_answer ? (
                <Rephrasable id={`why-${st.step_id}`} kind="Why" title={v.my_answer.correct ? "Correct" : "Not the recommended action"} text={v.my_answer.feedback}>
                  <section className={`verdict ${v.my_answer.correct ? "ok" : "no"}`} role="status">
                    <span className="head">{v.my_answer.correct ? "Correct" : "Not the recommended action"}</span>
                    <span className="fb">{v.my_answer.feedback}</span>
                  </section>
                </Rephrasable>
              ) : null}
            </>
          ) : (
            <section className="card tight">
              <span className="bold">Staff decide this step.</span>
              <span className="small muted">Their answers appear on the right. Discuss the reasoning before moving on.</span>
            </section>
          )}
          {v.restore_check_available ? (
            <section className="card" aria-label="Restore check">
              <div className="row-between">
                <div className="stack-sm" style={{ gap: 2 }}>
                  <h2>Would your backup actually work?</h2>
                  <span className="small muted">This runs a real restore test on the clinic's backup.</span>
                </div>
                <span className="pill pill-sim">Simulated backup</span>
              </div>
              {tested && busy !== "restore" ? <RestoreFacts r={tested} /> : (
                <button type="button" className="btn btn-primary btn-lg" style={{ alignSelf: "flex-start" }} disabled={!!busy} onClick={onRestore}>
                  {busy === "restore" ? "Testing the backup…" : "Test the backup now"}
                </button>
              )}
            </section>
          ) : null}
        </div>
        <aside className="col-side">
          <section className="list" aria-label="Team">
            <h2 style={{ fontSize: 18, margin: "12px 0 4px" }}>Team · {v.team.answered} of {v.team.total} answered</h2>
            {v.team.players.filter((p) => p.has_options).map((p) => (
              <div key={p.player_id} className="list-row">
                <span>{p.name}</span>
                {!p.answered && !(p.name in verdict) ? <span className="small muted">Choosing…</span>
                  : p.name in verdict ? <StatusPill status={verdict[p.name] ? "ok" : "under_attack"} label={verdict[p.name] ? "Correct" : "Incorrect"} />
                  : <StatusPill status="protected" label="Answered" />}
              </div>
            ))}
          </section>
          <button type="button" className="btn btn-dark btn-lg btn-block" disabled={!!busy || !v.can_advance} onClick={onAdvance}>{nextLabel}</button>
          <button type="button" className="btn btn-ghost" disabled={!!busy} onClick={onEnd}>End drill now</button>
        </aside>
      </div>
    </>
  );
}

export function RestoreFacts({ r }) {
  const days = Math.round(r.backup_age_hours / 24);
  const ok = r.result === "PASS";
  return (
    <>
      <div className="tinted row" style={{ background: ok ? "var(--green-soft)" : "var(--red-soft)" }}>
        <Pill tone={ok ? "green" : "red"} noDot>{r.result}</Pill>
        <span className="bold">{ok ? "This backup would bring your files back." : "Restoring now would have lost data."}</span>
      </div>
      <div className="facts">
        <div className="fact"><span className="k">Fresh?</span><span className="v">{days} days old</span></div>
        <div className="fact"><span className="k">Intact?</span><span className="v">{r.files_ok} of {r.files_total} files</span>
          <span className="small muted">{r.files_total - r.files_ok} damaged</span></div>
        <div className="fact"><span className="k">Out of reach?</span><span className="v">{r.exposed ? "Always plugged in" : "Kept unplugged"}</span>
          {r.exposed ? <span className="small muted">an attack can reach it</span> : null}</div>
      </div>
    </>
  );
}

function Results({ v, onNew }) {
  const r = v.results;
  const prev = PREVIOUS_DRILL.scenario_id === v.scenario_id ? PREVIOUS_DRILL : null;
  return (
    <>
      <div className="owner-head"><div><span className="small muted">{v.title}</span><h1>Debrief · team {r.team.correct} of {r.team.total} correct</h1></div></div>
      <section className="card">
        <div className="table-wrap">
          <table className="simple">
            <thead><tr><th scope="col">Person</th><th scope="col">Result</th><th scope="col">Actions to review</th></tr></thead>
            <tbody>
              {r.players.map((p) => {
                const t = playerTotal(p);
                return (
                  <tr key={p.name}>
                    <th scope="row" className="nowrap">{p.name}</th>
                    <td className="nowrap">{t.correct} of {t.total}</td>
                    <td className={p.missed_actions.length ? undefined : "muted"}>{missedText(p)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {r.restore ? <span className="small">Backup restore check: <strong>{r.restore.result}</strong></span> : null}
      </section>
      {prev ? <section className="card"><Retest prev={prev} right={r.team.correct} total={r.team.total} /></section> : null}
      <div className="row">
        <Link className="btn btn-primary" to="/owner/readiness">See readiness</Link>
        <button type="button" className="btn btn-soft" onClick={onNew}>Start another drill</button>
      </div>
    </>
  );
}
