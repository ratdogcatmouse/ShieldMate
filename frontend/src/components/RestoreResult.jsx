import { Pill, SimulatedBackupPill } from "./Badge.jsx";

// Result of a restore check: one line per check, with the fix when it failed.
export default function RestoreResult({ run, onRun, busy }) {
  if (!run) return null;
  const tested = run.result !== "NOT_TESTED";
  return (
    <section className="card">
      <div className="row-between">
        <h2>Backup check</h2>
        <Pill tone={run.result === "PASS" ? "green" : run.result === "FAIL" ? "red" : "grey"} small>
          {tested ? (run.result === "PASS" ? "Safe to restore" : "Not safe") : "Not tested yet"}
        </Pill>
      </div>
      {run.simulated_backup && <SimulatedBackupPill />}
      {run.checks.map((c) => (
        <div key={c.check} className="stack-sm" style={{ gap: 2 }}>
          <span className="bold" style={{ color: c.passed ? "var(--green-text)" : "var(--red-text)" }}>
            {c.passed ? "✓" : "✗"} {c.detail}
          </span>
          {!c.passed && c.fix && <span className="small muted">{c.fix}</span>}
          {c.failed_files?.length > 0 && (
            <span className="small mono">{c.failed_files.join(", ")}</span>
          )}
        </div>
      ))}
      {onRun && (
        <button type="button" className="btn btn-primary" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={onRun}>
          {busy ? "Testing the backup…" : "Test backup now"}
        </button>
      )}
    </section>
  );
}
