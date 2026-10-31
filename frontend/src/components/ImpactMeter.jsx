import { Pill } from "./Badge.jsx";

const STATE_TONE = { ok: "green", infected: "amber", isolated: "green", encrypting: "red", encrypted: "red" };
const SERVICE_TONE = { ok: "green", moved: "amber", down: "red", unavailable: "red" };

// What the drill's choices have done to each computer and the services on it.
export default function ImpactMeter({ impact }) {
  if (!impact || impact.length === 0) return null;
  return (
    <section className="card tight" aria-label="What this means for the clinic">
      <span className="section-label">At the clinic right now</span>
      {impact.map((d) => (
        <div key={d.device} className="stack-sm" style={{ gap: 4 }}>
          <div className="row-between">
            <span className="bold">{d.device}</span>
            <Pill tone={STATE_TONE[d.state] || "grey"} small>{d.state}</Pill>
          </div>
          {d.services.map((s) => (
            <div key={s.name} className="row" style={{ gap: 6 }}>
              <Pill tone={SERVICE_TONE[s.status] || "grey"} dot={false} small>{s.name}: {s.status}</Pill>
              {s.note && <span className="small muted">{s.note}</span>}
            </div>
          ))}
        </div>
      ))}
    </section>
  );
}
