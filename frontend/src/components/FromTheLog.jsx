// log_fields are copied verbatim from alerts and may hold hostile text.
// Plain text nodes only; never dangerouslySetInnerHTML.
export default function FromTheLog({ fields }) {
  const entries = Object.entries(fields || {});
  if (entries.length === 0) return null;
  return (
    <details className="log">
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
