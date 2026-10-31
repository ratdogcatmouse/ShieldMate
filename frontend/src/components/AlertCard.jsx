import { fmtTime } from "../format.js";
import { Pill, SimulatedPill } from "./Badge.jsx";
import FromTheLog from "./FromTheLog.jsx";
import Steps from "./Steps.jsx";

// Staff phone card: headline, what we know, steps, why, log details, and the "I've done these" button.
export default function AlertCard({ alert, it, onDone, busy, handled }) {
  const { card } = alert;
  const open = alert.status === "new" && !handled;
  const urgent = alert.severity === "needs_you_now";
  return (
    <>
      <article className="card">
        {open ? (
          <Pill tone={urgent ? "red" : "amber"}>
            {urgent ? "Needs you now" : "Heads-up"} · {fmtTime(alert.last_seen)}
          </Pill>
        ) : (
          <Pill tone="green">Handled · {fmtTime(alert.last_seen)}</Pill>
        )}
        {alert.count > 1 && <span className="small bold muted">Seen {alert.count} times</span>}
        <h1>{card.headline}</h1>
        <p className="ink-2">{card.what_we_know}</p>
        {alert.action?.simulated && <SimulatedPill />}
      </article>

      {card.steps.length > 0 && (
        <>
          <div className="row-between" style={{ padding: "0 4px" }}>
            <h2 style={{ fontSize: 18 }}>Do these now</h2>
            <span className="small muted">{card.steps.length} steps</span>
          </div>
          <Steps steps={card.steps} call={it && { name: it.it_contact_name, phone: it.it_contact_phone }} />
        </>
      )}

      <p className="small ink-2" style={{ padding: "0 4px" }}>
        <strong>Why this matters:</strong> {card.why}
      </p>

      <FromTheLog fields={card.log_fields} />

      {open ? (
        <div className="stack-sm" style={{ marginTop: 6 }}>
          <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy} onClick={onDone}>
            Tell Dr. Rao I've done these
          </button>
          {/* THAT_WAS_ME slot (features.js): "That was me" ghost button goes here. Not built. */}
        </div>
      ) : (
        <div className="card tight" role="status" style={{ background: "var(--green-soft)" }}>
          <span className="bold" style={{ color: "var(--green-text)" }}>Dr. Rao has been told</span>
          <span className="small">Follow the steps until he says otherwise.</span>
        </div>
      )}
    </>
  );
}
