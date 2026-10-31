// Segmented "moment N of M" bar.
export default function TeamProgress({ index, count, phase, gameTime }) {
  return (
    <div className="stack-sm">
      <div className="row-between small">
        <span className="bold">Moment {index + 1} of {count}{phase ? ` · ${phase}` : ""}</span>
        {gameTime && <span className="muted">{gameTime} at the clinic</span>}
      </div>
      <div
        className="progress-segs"
        role="img"
        aria-label={`Moment ${index + 1} of ${count}`}
        style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: count }, (_, i) => <span key={i} className={i <= index ? "on" : undefined} />)}
      </div>
    </div>
  );
}
