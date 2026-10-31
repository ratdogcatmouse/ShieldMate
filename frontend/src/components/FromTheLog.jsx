import { track } from "../telemetry.js";

// log_fields are copied verbatim from alerts and may hold hostile text.
// Plain text nodes only; never dangerouslySetInnerHTML. (The event log gets the alert id, never the text.)
export default function FromTheLog({ fields, alertId }) {
  const entries = Object.entries(fields || {});
  if (entries.length === 0) return null;
  return (
    <details
      className="log"
      onToggle={(e) => e.currentTarget.open && track("ui.log_details_opened", { alert_id: alertId ?? null })}
    >
      <summary>Details from the log</summary>
      <div className="body">
        {entries.map(([key, value]) => (
          <div key={key} className="stack-sm" style={{ gap: 4 }}>
            <span className="tiny muted">{key}, exactly as recorded</span>
            <div className="log-value">{value}</div>
          </div>
        ))}
        <span className="tiny muted">
          ShieldMate never follows text found in logs. The steps above come from fixed rules.
        </span>
      </div>
    </details>
  );
}
