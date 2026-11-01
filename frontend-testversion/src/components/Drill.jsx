// Pieces shared by the staff and owner drill screens.
import { ACTION_LABEL, PHASE_LABEL } from "../lib/content.js";
import { Check, Cross } from "./Icons.jsx";
import { Pill } from "./ui.jsx";

// What the story's computers mean for the clinic right now: "Billing down", "Check-in moved".
export function ImpactPills({ impact }) {
  const items = impact.flatMap((d) =>
    d.services.filter((s) => s.status !== "ok").map((s) => ({ key: `${d.device}-${s.name}`, ...s })));
  if (!items.length) return null;
  return (
    <div className="row" style={{ gap: 6 }}>
      {items.map((s) => (
        <Pill key={s.key} tone={s.status === "moved" ? "amber" : "red"} small noDot>
          {s.status === "moved" ? `${s.name}: ${s.note || "moved"}` : `${s.name} ${s.status}`}
        </Pill>
      ))}
    </div>
  );
}

// The player's options for this step. Before answering they are buttons; afterwards the
// chosen one shows right or wrong (the server only reveals the key for your own answer).
export function Options({ view, onAnswer, disabled, letters = "ABCD" }) {
  const mine = view.my_answer;
  const canAnswer = !mine && view.status === "open";
  return (
    <div className="options" role="group" aria-label="Answers">
      {view.options.map((o, i) => {
        if (canAnswer) {
          return (
            <button key={o.option_id} type="button" className="option" disabled={disabled} onClick={() => onAnswer(o.option_id)}>
              <span className="mark">{letters[i]}</span><span>{o.text}</span>
            </button>
          );
        }
        if (mine && mine.option_id === o.option_id) {
          return (
            <div key={o.option_id} className={`option ${mine.correct ? "right" : "wrong"}`}>
              <span className="mark">{mine.correct ? <Check /> : <Cross />}</span>
              <span>{o.text}<span className="tag">{mine.correct ? "Your answer · correct" : "Your answer"}</span></span>
            </div>
          );
        }
        return (
          <div key={o.option_id} className="option dim">
            <span className="mark">{letters[i]}</span><span>{o.text}</span>
          </div>
        );
      })}
    </div>
  );
}

// A player's total across the phases the drill reached.
export function playerTotal(p) {
  return Object.values(p.by_phase).reduce((acc, s) => ({ correct: acc.correct + s.correct, total: acc.total + s.total }),
    { correct: 0, total: 0 });
}

export function missedText(p) {
  return p.missed_actions.length ? p.missed_actions.map((a) => ACTION_LABEL[a] || a).join("; ") : "Nothing";
}

// Results per phase for one player, as rows of ticks.
export function PhaseRows({ results, player }) {
  return (
    <section className="list" aria-label="Your answers by stage">
      {results.phases.map((ph) => {
        const s = player.by_phase[ph];
        if (!s || !s.total) return null;
        const ok = s.correct === s.total;
        return (
          <div key={ph} className="list-row" style={{ justifyContent: "flex-start", gap: 12 }}>
            <span className="check" style={{ width: 26, height: 26, border: 0, background: ok ? "var(--green)" : "var(--red)", color: "#fff" }} aria-hidden="true">
              {ok ? <Check /> : <Cross />}
            </span>
            <span className="stack-sm" style={{ gap: 0 }}>
              <span className="bold">{PHASE_LABEL[ph]}</span>
              <span className="small muted">{s.correct} of {s.total} correct</span>
            </span>
          </div>
        );
      })}
    </section>
  );
}

// Progress bar segments: one per step, lit up to the current one.
export function Segments({ index, count }) {
  return (
    <div className="progress-segs" role="img" aria-label={`Step ${index + 1} of ${count}`}
      style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}>
      {Array.from({ length: count }, (_, i) => <span key={i} className={i <= index ? "on" : undefined} />)}
    </div>
  );
}
