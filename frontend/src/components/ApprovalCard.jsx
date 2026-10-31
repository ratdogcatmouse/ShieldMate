import { fmtTime, mmss } from "../format.js";
import { Icon } from "../icons.jsx";
import { Pill, SimulatedPill } from "./Badge.jsx";

// The owner's block request (flag ACTIONS). Proposed by fixed rules, never by AI.
export default function ApprovalCard({ action, alert, standingRule, onApprove, onDecline, busy }) {
  const wait = standingRule ? "Your rule blocks it" : "Backup person is asked";
  return (
    <article className="card outlined">
      <Pill tone="red">Your decision needed</Pill>
      <h1>Block the attacker on {action.agent_name} for 1 hour?</h1>
      <p className="ink-2">
        {alert ? `${alert.count} wrong passwords from ` : "Attacks from "}
        <span className="mono">{action.target_ip}</span>.
      </p>
      <div className="facts">
        <div className="fact"><span className="k">What it does</span><span className="v">Stops only that address</span></div>
        <div className="fact"><span className="k">How long</span><span className="v">1 hour</span></div>
        <div className="fact"><span className="k">If you don't answer</span><span className="v">{wait}</span></div>
      </div>
      {action.seconds_left !== null && (
        <div className="tinted row nowrap" style={{ gap: 8 }}>
          <Icon name="clock" />
          <span>Time left to answer: <strong>{mmss(action.seconds_left)}</strong></span>
        </div>
      )}
      <div className="btn-group">
        <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={onApprove}>Approve block</button>
        <button type="button" className="btn btn-soft btn-lg" disabled={busy} onClick={onDecline}>Decline</button>
      </div>
      <span className="small muted">Proposed by ShieldMate's fixed rules, not by AI.</span>
      {action.simulated && <SimulatedPill />}
      {/* NOTIFY_PREVIEW slot (features.js): phone-notification preview of this request goes here. Not built. */}
    </article>
  );
}

// A request that has been answered.
export function DecidedCard({ action }) {
  const blocked = action.status === "executed" || action.status === "approved";
  return (
    <article className="card" role="status">
      <Pill tone={blocked ? "green" : "grey"} dot={blocked}>
        {blocked ? `Blocked · ${fmtTime(action.decided_at)}` : `${action.status[0].toUpperCase()}${action.status.slice(1)}`}
      </Pill>
      <h1>{action.label}</h1>
      {action.expires_at && <p className="ink-2">It lifts by itself at {fmtTime(action.expires_at)}.</p>}
      {action.refused_reason && <p className="ink-2">{action.refused_reason}</p>}
      {action.simulated && <SimulatedPill />}
    </article>
  );
}
