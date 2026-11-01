// Notifications on a staff phone. An attack note can carry a one-tap block button.
import { Pill } from "./ui.jsx";
import { blockButton } from "../lib/notifications.js";
import { ago } from "../lib/time.js";

// One note. `onBlock(note)` runs when the button is tapped; `busy` disables it while a tap is in flight.
export function NoteRow({ n, busy, onBlock }) {
  const attack = n.kind === "attack";
  const btn = blockButton(n.quick_action, n.expiresAt);
  return (
    <article className={`card tight ${attack ? "note-attack" : "note-info"}`} aria-label={attack ? "Attack notification" : "Notification"}>
      <div className="row-between">
        <Pill tone={attack ? "red" : "grey"} small>{attack ? "Attack" : "Info"}</Pill>
        <span className="tiny muted">{ago(n.created_at)}</span>
      </div>
      {/* The text is log-derived; React shows it as text, never as markup. */}
      <span className={attack ? "bold" : ""}>{n.text}</span>
      {btn ? (
        <button type="button" className={`btn ${btn.disabled ? "btn-soft" : "btn-primary"}`} disabled={btn.disabled || !!busy} onClick={() => onBlock(n)}>
          {btn.label}
        </button>
      ) : null}
    </article>
  );
}

// The latest few notes, newest first. Nothing when there are none.
export function NoteList({ notes, busy, onBlock, max = 3 }) {
  if (!notes?.length) return null;
  return (
    <section className="stack-sm" aria-label="Notifications">
      {[...notes].reverse().slice(0, max).map((n) => <NoteRow key={n.id} n={n} busy={busy} onBlock={onBlock} />)}
    </section>
  );
}
