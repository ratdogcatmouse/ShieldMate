import { Pill } from "./Badge.jsx";

const STATUS = {
  ok: ["green", "Working normally"],
  under_attack: ["red", "Under attack"],
  protected: ["green", "Protected"],
};

// "Computers" list. `devices` come from /devices (with status) or /clinic (without).
export default function DeviceStrip({ devices }) {
  return (
    <section className="list" aria-label="Computers">
      <h2 style={{ fontSize: 18, margin: "12px 0 4px" }}>Computers</h2>
      {devices.map((d) => {
        const [tone, label] = d.status ? STATUS[d.status] || ["grey", d.status] : ["grey", d.location];
        return (
          <div className="list-row" key={d.id}>
            <span>{d.agent_name}<span className="small muted"> · {d.location}</span></span>
            <Pill tone={tone} small>{label}</Pill>
          </div>
        );
      })}
    </section>
  );
}
