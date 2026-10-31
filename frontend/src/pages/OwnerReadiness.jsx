// Owner: Readiness. Backup restore check, team practice, and who can act if the owner is away.
import { useNavigate } from "react-router-dom";
import { missedText, playerTotal } from "../components/Drill.jsx";
import { OwnerShell } from "../components/Shells.jsx";
import { Pill, Retest, StatusPill, useAction } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { PREVIOUS_DRILL } from "../lib/content.js";
import { ownerOf } from "../lib/derive.js";
import { getLastDrill, getPlayer, setLastDrill, setPlayer } from "../lib/session.js";
import { fmtTime } from "../lib/time.js";
import { usePoll } from "../lib/usePoll.js";

// The owner's last drill, if this device ran one and it has finished.
async function lastDrill(owner) {
  const code = getLastDrill();
  const pid = code && getPlayer(code, owner.id);
  if (!pid) return null;
  try {
    const v = await api.getDrill(code, pid);
    return v.status === "finished" ? v : null;
  } catch {
    return null;   // gone after a Reset
  }
}

export default function OwnerReadiness() {
  const navigate = useNavigate();
  const [run, busy] = useAction();
  const { data, stale, refresh } = usePoll(async () => {
    const [clinic, restore] = await Promise.all([api.getClinic(), api.getRestoreLatest()]);
    const owner = ownerOf(clinic);
    return { clinic, owner, restore, drill: await lastDrill(owner) };
  }, 3000);

  const test = () => run("restore", async () => {
    await new Promise((r) => setTimeout(r, 1500));
    await api.runRestore();
    await refresh();
  });
  const startDrill = () => run("drill", async () => {
    const r = await api.createDrill("ransomware_clinic", data.owner.id);
    setPlayer(r.code, data.owner.id, r.player_id);
    setLastDrill(r.code);
    navigate(`/owner/drill?code=${r.code}`);
  });

  return (
    <OwnerShell clinicName={data?.clinic.clinic.name} ownerName={data?.owner?.name} stale={stale}>
      <div className="owner-head"><div><span className="owner-mobile-head">{data?.clinic.clinic.name}</span><h1>Readiness</h1></div></div>
      {!data ? <p className="muted">Loading…</p> : (
        <>
          <Summary restore={data.restore} drill={data.drill} gaps={data.clinic.single_point_of_failure} />
          <div className="grid-auto">
            <BackupCard r={data.restore} testing={busy === "restore"} disabled={!!busy} onTest={test} />
            <TeamCard v={data.drill} disabled={!!busy} onStart={startDrill} />
            <AwayCard gaps={data.clinic.single_point_of_failure} />
          </div>
        </>
      )}
    </OwnerShell>
  );
}

const teamOk = (v) => v && v.results.team.total && v.results.team.correct / v.results.team.total >= 0.7;

function Summary({ restore, drill, gaps }) {
  const bad = restore.result === "FAIL";
  const untested = restore.result === "NOT_TESTED";
  let line;
  if (untested) line = "You haven't tested your backup yet. Start there.";
  else if (bad && drill) line = teamOk(drill) ? "Your team knows most steps, but your backup wouldn't save you." : "Your team needs more practice, and your backup wouldn't save you.";
  else if (bad) line = "Your backup wouldn't save you. Fix it, then practise with the team.";
  else line = drill ? "Your backup works and your team has practised." : "Your backup works. Next, practise with the team.";
  const count = (untested || bad ? 1 : 0) + (teamOk(drill) ? 0 : 1) + (gaps.length ? 1 : 0);
  return (
    <section className="card dark" style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
      <div className="stack-sm grow" style={{ gap: 4, minWidth: 260 }}>
        <span className="on-dark-muted small">If ransomware hit today</span>
        <span style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.25 }}>{line}</span>
      </div>
      <span className="on-dark-muted">{count} thing{count === 1 ? "" : "s"} to fix</span>
    </section>
  );
}

function BackupCard({ r, testing, disabled, onTest }) {
  const yn = (ok) => <span className="bold" style={{ color: ok ? "var(--green-ink)" : "var(--red-ink)" }}>{ok ? "Yes" : "No"}</span>;
  const check = (name) => r.checks.find((c) => c.check === name);
  const failed = check("integrity")?.failed_files || [];
  const fixes = r.checks.filter((c) => !c.passed).map((c) => c.fix);
  return (
    <section className="card" id="backup">
      <div className="row-between">
        <h2>Backup restore check</h2>
        {r.result === "FAIL" ? <StatusPill status="under_attack" label="Not safe" /> : r.result === "PASS" ? <StatusPill status="ok" label="Safe" /> : <Pill tone="grey" small>Not tested</Pill>}
      </div>
      {r.simulated_backup !== false ? <span className="pill pill-sim">Simulated backup</span> : null}
      {testing ? <p className="ink-2" role="status">Restoring sample files into a separate folder and checking each one…</p>
        : r.result === "NOT_TESTED" ? <p className="ink-2">A green "backup succeeded" message isn't proof. This restores sample files and checks each one is intact.</p>
        : (
          <>
            <div className="list" style={{ padding: 0, background: "transparent" }}>
              {["freshness", "integrity", "exposure"].map((name) => {
                const c = check(name);
                if (!c) return null;
                const q = { freshness: "Fresh?", integrity: "Intact?", exposure: "Out of reach?" }[name];
                return <div key={name} className="list-row"><span><strong>{q}</strong> {c.detail}</span>{yn(c.passed)}</div>;
              })}
            </div>
            {failed.length ? (
              <details className="log">
                <summary>The {failed.length} damaged files</summary>
                <div className="body">{failed.map((f) => <div key={f} className="log-value">{f}</div>)}</div>
              </details>
            ) : null}
            {fixes.length ? <div className="tinted"><strong>Fix:</strong> {fixes.join(" ")}</div> : null}
          </>
        )}
      <div className="row">
        <button type="button" className="btn btn-primary" disabled={disabled} onClick={onTest}>
          {testing ? "Testing…" : r.result === "NOT_TESTED" ? "Test the backup" : "Test again"}
        </button>
        {r.started_at && !testing ? <span className="small muted">Last test {fmtTime(r.started_at)}</span> : null}
      </div>
    </section>
  );
}

function TeamCard({ v, disabled, onStart }) {
  if (!v) {
    return (
      <section className="card">
        <div className="row-between"><h2>Team practice</h2><Pill tone="grey" small>No drill yet</Pill></div>
        <p className="ink-2">Run a 6-minute ransomware drill with your team on their phones.</p>
        <button type="button" className="btn btn-primary" style={{ alignSelf: "flex-start" }} disabled={disabled} onClick={onStart}>Start a team drill</button>
      </section>
    );
  }
  const r = v.results;
  const ok = teamOk(v);
  const prev = PREVIOUS_DRILL.scenario_id === v.scenario_id ? PREVIOUS_DRILL : null;
  return (
    <section className="card span-2">
      <div className="row-between"><h2>Team practice</h2><Pill tone={ok ? "amber" : "red"} small>{ok ? "Mostly ready" : "Needs practice"}</Pill></div>
      <span className="small muted">{v.title} · code {v.code} · team {r.team.correct} of {r.team.total}</span>
      <div className="table-wrap">
        <table className="simple">
          <thead><tr><th scope="col">Person</th><th scope="col">Result</th><th scope="col">Still to learn</th></tr></thead>
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
      <Retest prev={prev} right={r.team.correct} total={r.team.total} />
      <button type="button" className="btn btn-primary" style={{ alignSelf: "flex-start" }} disabled={disabled} onClick={onStart}>Start another drill</button>
    </section>
  );
}

// Single points of failure come from the server (GET /clinic): a capability only one person has.
function AwayCard({ gaps }) {
  return (
    <section className="card">
      <div className="row-between"><h2>If you're away</h2>{gaps.length ? <Pill tone="amber" small>Gap</Pill> : <Pill tone="green" small>Covered</Pill>}</div>
      {gaps.length ? (
        <>
          {gaps.map((g) => <p key={g.capability} className="ink-2">Only {g.only} can {g.label.toLowerCase()}. If they're with a patient or on leave, nobody can.</p>)}
          <span className="small muted">Choosing a second person is part of setup (after the demo).</span>
        </>
      ) : <p className="ink-2">At least two people can restore backups and approve downtime.</p>}
    </section>
  );
}
