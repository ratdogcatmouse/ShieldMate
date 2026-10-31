// Mission control: the projector screen the audience watches while staff use their phones.
// Read-only. The clinic floor plan, the attack, the "spotted → blocked" stopwatch, the CERT-In
// clock, the drill scoreboard, people and a live feed.
import * as api from "../lib/api.js";
import { DEVICE_STATUS, ROLE_LABEL, stepShort } from "../lib/content.js";
import {
  activity, certinDue, deviceStates, ownerOf, passwordAlert, ransomwareAlert, sourceBadge, staffName,
} from "../lib/derive.js";
import { getPlayer, setPlayer } from "../lib/session.js";
import { fmtTime, useNow } from "../lib/time.js";
import { usePoll } from "../lib/usePoll.js";
import { Countdown, FeedTag, Stopwatch, TimeLeft } from "../components/ui.jsx";

const TONE = { green: "#22C55E", red: "#F04438", blue: "#38BDF8", amber: "#F5A524", grey: "#7C8BA5" };
// Floor plan rooms (viewBox 900 x 470), one per device.
const ROOMS = [
  { agent: "RECEPTION-PC", label: "RECEPTION", x: 20, w: 280 },
  { agent: "FILE-SERVER", label: "SERVER CUPBOARD", x: 310, w: 280 },
  { agent: "DOCTOR-PC", label: "DOCTOR'S ROOM", x: 600, w: 280 },
];
const nodeAt = (agent) => {
  const r = ROOMS.find((x) => x.agent === agent);
  return r ? { x: r.x + r.w / 2, y: 190 } : null;
};
const HOT = ["under_attack", "files_locked", "encrypted", "encrypting", "infected"];

// The drill as the host sees it (mission control runs on the owner's laptop): joining again
// returns the host's own player.
async function drillView(owner) {
  const cur = (await api.getCurrentDrill()).drill;
  if (!cur) return null;
  let pid = getPlayer(cur.code, owner.id);
  if (!pid) {
    pid = (await api.joinDrill(cur.code, owner.id)).player_id;
    setPlayer(cur.code, owner.id, pid);
  }
  return api.getDrill(cur.code, pid);
}

async function load() {
  const clinic = await api.getClinic();
  const [status, owner, staffList, actions, devices, notes, drill] = await Promise.all([
    api.getStatus(),
    api.getAlerts("owner", { includeClosed: true }),
    api.getAlerts("front_desk"),            // staff step progress for the people panel
    api.listOrEmpty(api.getActions(), "actions"),
    api.listOrEmpty(api.getDevices(), "devices"),
    api.getNotifications("owner"),
    drillView(ownerOf(clinic)).catch(() => null),
  ]);
  const open = owner.alerts.filter((a) => !a.it.closed_at);
  return { clinic, status, alerts: open, feed: activity(clinic, owner.alerts, actions, notes.notifications), hidden: owner.hidden_count, staffAlerts: staffList.alerts, actions, devices,
           notes: notes.notifications, drill };
}

export default function Mission() {
  const now = useNow();
  const { data } = usePoll(load, 2000);
  if (!data) return <main className="mc"><p>Loading…</p></main>;

  const { clinic, drill } = data;
  const pw = passwordAlert(data.alerts.filter((a) => a.status !== "mine"));
  const rw = ransomwareAlert(data.alerts);
  const act = pw?.action ? data.actions.find((x) => x.id === pw.action.id) : null;
  let devices = deviceStates(clinic, data.devices.length ? data.devices : null, data.alerts);
  if (drill && drill.status !== "finished" && drill.impact.length) {
    // In a drill the floor plan tells the drill's story, marked as practice.
    const story = Object.fromEntries(drill.impact.map((d) => [d.device, d.state]));
    devices = devices.map((d) => {
      const st = story[d.agent];
      if (!st || st === "ok") return d;
      return { ...d, status: st, ...DEVICE_STATUS[st], label: `${DEVICE_STATUS[st].label} (practice)` };
    });
  }
  const runningDrill = drill && drill.status !== "finished" ? drill : null;
  const ip = pw?.card.log_fields.source_ip || act?.target_ip;
  const attack = !runningDrill && pw ? { target: pw.agent_name, ip, blocked: act?.status === "executed" } : null;
  const state = runningDrill ? ["drill", "PRACTICE DRILL RUNNING"]
    : rw ? ["attack", "RANSOMWARE ON THE FILE SERVER"]
    : pw && act?.status === "failed" ? ["attack", "BLOCK DIDN'T TAKE EFFECT"]
    : pw && act?.status === "executed" ? ["blocked", "ATTACK BLOCKED"]
    : pw ? ["attack", "ATTACK IN PROGRESS"] : ["ok", "ALL QUIET"];
  const badge = sourceBadge(data.status);
  const rule = clinic.clinic.standing_rule_block_ip;

  return (
    <main className="mc" aria-live="polite">
      <header className="mc-head">
        <div className="mc-title">
          <svg width="38" height="38" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5z" fill="var(--blue)" />
            <path d="m8.5 12 2.5 2.5 4.5-5" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div className="stack-sm" style={{ gap: 0 }}>
            <span className="name">ShieldMate</span>
            <span className="sub">{clinic.clinic.name.toUpperCase()} · MISSION CONTROL</span>
          </div>
        </div>
        <span className={`mc-state ${state[0]}`} role="status">{state[1]}</span>
        <span style={{ color: "#7C8BA5", fontFamily: "var(--mono)" }}>{fmtTime(now)} · {badge.text.toLowerCase()}</span>
      </header>
      <div className="mc-grid">
        <section className="mc-panel">
          <span className="mc-label">{runningDrill ? "The clinic in the drill story" : "The clinic right now"}</span>
          <FloorPlan devices={devices} attack={attack} />
          <div className="mc-tags">
            <span>{data.hidden} routine event{data.hidden === 1 ? "" : "s"} filtered out</span>
            <span>Plain-language cards in English · ಕನ್ನಡ · हिन्दी</span>
            {rule ? <span>Standing rule on: auto-block after {clinic.clinic.approval_timeout_minutes} min</span> : null}
          </div>
        </section>
        <div className="mc-side">
          {/* A finished drill keeps its score up until the next real alert. */}
          {runningDrill || (drill?.status === "finished" && !pw && !rw) ? <DrillPanel v={drill} /> : <ClockPanel pw={pw} act={act} rw={rw} devices={devices} clinic={clinic} />}
          <People data={data} pw={pw} act={act} drill={runningDrill} />
          <section className="mc-panel" style={{ flex: 1, minHeight: 0 }}>
            <span className="mc-label">Live feed</span>
            <div className="mc-feed">
              {data.feed.length ? data.feed.slice(0, 8).map((e, i) => (
                <div key={i} className="ev"><time>{fmtTime(e.at)}</time><FeedTag tag={e.tag} /><span>{e.text}</span></div>
              )) : <span style={{ color: "#7C8BA5" }}>Nothing yet.</span>}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}

function FloorPlan({ devices, attack }) {
  const target = attack && nodeAt(attack.target);
  const label = devices.map((d) => `${d.short} ${d.label}`).join(", ") + (attack ? `. Attack from ${attack.ip}${attack.blocked ? " blocked" : ""}` : "");
  return (
    <svg viewBox="0 0 900 470" width="100%" role="img" aria-label={`Clinic floor plan: ${label}`}>
      {ROOMS.map((r) => (
        <g key={r.agent}>
          <rect className="room" x={r.x} y="20" width={r.w} height="330" rx="18" />
          <text className="room-label" x={r.x + 20} y="52">{r.label}</text>
        </g>
      ))}
      {attack && target ? (
        <g>
          {/* The attacker on the Wi-Fi, outside the rooms; the line comes in from the target's left. */}
          <path className="attack-line" d={`M110 420 C 40 380, 30 ${target.y}, ${target.x - 64} ${target.y}`}
            style={attack.blocked ? { stroke: "#7C8BA5", animation: "none" } : undefined} />
          <circle cx="110" cy="420" r="22" fill="#3A1114" stroke={attack.blocked ? "#7C8BA5" : "#F04438"} strokeWidth="3" />
          <text x="110" y="426" textAnchor="middle" fill="#FCA5A5" fontSize="18" fontWeight="700">?</text>
          <text className="node-sub" x="144" y="416">Unknown device on Wi-Fi</text>
          <text className="node-sub" x="144" y="436" style={{ fontFamily: "var(--mono)" }}>{attack.ip || ""}</text>
          {attack.blocked ? (
            <>
              <g transform="translate(22 300)">
                <path d="M22 0 4 7v14c0 12 8 21 18 25 10-4 18-13 18-25V7z" fill="#38BDF8" stroke="#0B1220" strokeWidth="3" />
                <path d="m13 23 6 6 11-12" fill="none" stroke="#0B1220" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
              </g>
              <text x="144" y="460" fill="#7DD3FC" fontSize="18" fontWeight="700" letterSpacing="1">BLOCKED · CAN'T REACH THE CLINIC</text>
            </>
          ) : null}
        </g>
      ) : null}
      {devices.map((d) => {
        const p = nodeAt(d.agent);
        if (!p) return null;
        return (
          <g key={d.agent}>
            {HOT.includes(d.status) ? <circle className="pulse" cx={p.x} cy={p.y} r="56" /> : null}
            <rect className={`node ${d.status}`} x={p.x - 62} y={p.y - 50} width="124" height="100" rx="16" />
            <rect x={p.x - 34} y={p.y - 30} width="68" height="42" rx="5" fill="none" stroke="#E6EDF7" strokeWidth="3" />
            <path d={`M${p.x - 14} ${p.y + 24}h28`} stroke="#E6EDF7" strokeWidth="3" strokeLinecap="round" />
            <text className="node-label" x={p.x} y={p.y + 86} textAnchor="middle">{d.short}</text>
            <text className="node-sub" x={p.x} y={p.y + 108} textAnchor="middle" style={{ fill: TONE[d.tone] || "#A9B6CC" }}>{d.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function ClockPanel({ pw, act, rw, devices, clinic }) {
  if (rw) {
    const due = certinDue(rw);
    return (
      <section className="mc-panel">
        <span className="mc-label">Report to CERT-In within 6 hours</span>
        <span className="mc-big nowrap" style={{ color: "#FCA5A5", fontSize: 52 }}>{due ? <TimeLeft toMs={due} /> : null}</span>
        <span style={{ color: "#A9B6CC" }}>Spotted at {fmtTime(rw.first_seen)} · the report is drafted from this timeline</span>
      </section>
    );
  }
  if (pw) {
    const done = act?.status === "executed";
    const failed = act?.status === "failed";
    const how = !act ? "No block proposed"
      : done ? (act.decided_via === "standing_rule" ? "Blocked by the standing rule" : `Blocked: ${staffName(clinic, act.decided_by)} tapped Approve`)
      : act.status === "proposed" ? "Waiting for the owner to approve"
      : failed ? "The block didn't take effect: call IT" : `Block ${act.status}`;
    const due = act?.status === "proposed" ? new Date(Date.parse(act.proposed_at) + clinic.clinic.approval_timeout_minutes * 60000).toISOString() : null;
    return (
      <section className="mc-panel">
        <span className="mc-label">{failed ? "Attack still going: block didn't take effect" : "Attack spotted → blocked"}</span>
        <span className="mc-big" style={{ color: done ? "#7DD3FC" : "#FCA5A5" }}><Stopwatch from={pw.first_seen} stop={done ? act.decided_at : null} /></span>
        <span style={{ color: "#A9B6CC" }}>{how}</span>
        {due && act.on_timeout === "block_under_standing_rule" ? (
          <span style={{ color: "#FCD34D" }}>Auto-blocks in <strong><Countdown to={due} /></strong> if nobody answers</span>
        ) : null}
      </section>
    );
  }
  return (
    <section className="mc-panel">
      <span className="mc-label">Watching</span>
      <span className="mc-big" style={{ color: "#4ADE80" }}>{devices.filter((d) => d.status === "ok").length} / {devices.length}</span>
      <span style={{ color: "#A9B6CC" }}>computers reporting · nothing needs anyone right now</span>
    </section>
  );
}

function DrillPanel({ v }) {
  return (
    <section className="mc-panel">
      <span className="mc-label">Drill · code {v.code}</span>
      {v.status === "lobby" ? (
        <>
          <span className="mc-big" style={{ color: "#FCD34D", fontSize: 52 }}>Join: {v.code}</span>
          <span style={{ color: "#A9B6CC" }}>{v.team.players.length} joined: {v.team.players.map((p) => p.name).join(", ")}</span>
        </>
      ) : v.status === "finished" ? (
        <span className="mc-big" style={{ color: "#FCD34D" }}>{v.results.team.correct} / {v.results.team.total}</span>
      ) : (
        <>
          <span style={{ fontSize: 20, fontWeight: 700 }}>Moment {v.step_index + 1} of {v.step_count} · {v.step.game_time}</span>
          <span style={{ color: "#A9B6CC", fontSize: 17 }}>{stepShort(v.scenario_id, v.step)}</span>
          <div className="score-row"><span>Answered</span><strong>{v.team.answered} / {v.team.total}</strong></div>
          {v.review ? (
            <div className="score-row"><span>Right this moment</span>
              <strong style={{ color: "#FCD34D" }}>{v.review.answers.filter((a) => a.correct).length} / {v.review.answers.length}</strong></div>
          ) : null}
        </>
      )}
    </section>
  );
}

function People({ data, pw, act, drill }) {
  const { clinic } = data;
  const staffPw = pw && data.staffAlerts.find((a) => a.id === pw.id);
  const rows = clinic.staff.map((p) => {
    let st = "All quiet";
    let col = "#22C55E";
    if (drill) {
      const t = drill.team.players.find((x) => x.name === p.name);
      if (drill.status === "lobby") { st = t ? "Joined" : "Not joined yet"; col = t ? "#22C55E" : "#7C8BA5"; }
      else if (!t || !t.has_options) { st = "Not in this moment"; col = "#7C8BA5"; }
      else { st = t.answered ? "Answered" : "Choosing…"; col = t.answered ? "#22C55E" : "#FCD34D"; }
    } else if (pw) {
      if (p.role === "owner") {
        st = act ? (act.status === "proposed" ? "Deciding on the block" : act.status === "executed" ? "Block approved" : `Block ${act.status}`) : "Has the alert";
        col = act?.status === "executed" ? "#38BDF8" : "#FCD34D";
      } else if (staffPw) {
        const steps = staffPw.card.steps;
        const d = steps.filter((x) => x.done).length;
        st = d === steps.length ? `All ${steps.length} steps done` : `${d} of ${steps.length} steps done`;
        col = d === steps.length ? "#22C55E" : "#FCD34D";
      }
    }
    return (
      <div key={p.id} className="mc-person">
        <span className="av">{p.name.replace("Dr. ", "").charAt(0)}</span>
        <span className="stack-sm" style={{ gap: 0 }}><strong>{p.name}</strong><span className="st">{ROLE_LABEL[p.role]} · {st}</span></span>
        <span className="dot" style={{ background: col }} />
      </div>
    );
  });
  // The clinic's IT contact, from whichever open incident they're handling.
  const inc = data.alerts.find((a) => a.it.status !== "none" && !a.it.closed_at);
  const it = inc?.it;
  const itState = !it ? ["Not needed right now", "#22C55E"]
    : it.status === "called" ? [`${staffName(clinic, it.called_by)} called · not picked up`, "#F04438"]
    : it.status === "received" ? [`On it since ${fmtTime(it.received_at)}`, "#FCD34D"]
    : ["Says it's fixed · owner checking", "#38BDF8"];
  return (
    <section className="mc-panel">
      <span className="mc-label">People</span>
      {rows}
      {!drill ? (
        <div className="mc-person">
          <span className="av">IT</span>
          <span className="stack-sm" style={{ gap: 0 }}><strong>{clinic.clinic.it_contact_name}</strong><span className="st">IT support · {itState[0]}</span></span>
          <span className="dot" style={{ background: itState[1] }} />
        </div>
      ) : null}
    </section>
  );
}
