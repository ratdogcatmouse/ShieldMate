// The "?" on a phone: while at least one alert or decision card is on screen it offers to say
// the ones you pick in simpler words. No text box and no chat.
//   <RephraseProvider role lang> wraps a screen and draws the "?" and its picker sheet.
//   <Rephrasable id kind title text alertId> wraps one card: it registers the card with the
//   picker while it is on screen and shows the "In simpler words" block right under it.
// The original card is never changed. Everything from the server is rendered as plain text.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { explainCard } from "../lib/rephrase.js";

const Ctx = createContext(null);

export function RephraseProvider({ role, lang, drillCode = null, children }) {
  const [cards, setCards] = useState({});     // id -> { id, kind, title, text, alertId }, in on-screen order
  const [results, setResults] = useState({}); // id -> { state: "loading" | "done" | "err" | "off", text }
  const [open, setOpen] = useState(false);
  const [off, setOff] = useState(false);      // the server said not_enabled: stop offering the "?"
  const live = useRef({ role, lang, drillCode, cards });
  live.current = { role, lang, drillCode, cards };   // read by in-flight calls, so a poll can't send stale values

  const register = useCallback((c) => setCards((prev) => {
    const p = prev[c.id];
    // Same card again (the screen polls every 2 s): keep the old object so nothing re-renders.
    if (p && p.kind === c.kind && p.title === c.title && p.text === c.text && p.alertId === c.alertId) return prev;
    return { ...prev, [c.id]: c };
  }), []);
  const unregister = useCallback((id) => setCards((prev) => {
    if (!(id in prev)) return prev;
    const { [id]: _gone, ...rest } = prev;
    return rest;
  }), []);
  const hide = useCallback((id) => setResults((r) => {
    const { [id]: _gone, ...rest } = r;
    return rest;
  }), []);

  const run = useCallback(async (ids) => {
    setResults((r) => ({ ...r, ...Object.fromEntries(ids.map((id) => [id, { state: "loading", text: "" }])) }));
    await Promise.all(ids.map(async (id) => {
      const card = live.current.cards[id];
      const res = card ? await explainCard(card, live.current) : { state: "err", text: "" };
      if (res.state === "off") setOff(true);
      setResults((r) => ({ ...r, [id]: res }));
    }));
  }, []);

  // Stable, so the page's 2 s polls (which re-render this) don't re-run the sheet's focus effect.
  const close = useCallback(() => setOpen(false), []);
  const runAndClose = useCallback((ids) => { setOpen(false); run(ids); }, [run]);

  const list = Object.values(cards);
  const value = useMemo(() => ({ register, unregister, results, hide, run }), [register, unregister, results, hide, run]);
  return (
    <Ctx.Provider value={value}>
      {children}
      {list.length && !off ? <Button onOpen={() => setOpen(true)} /> : null}
      {open && list.length ? <Sheet cards={list} onClose={close} onRun={runAndClose} /> : null}
    </Ctx.Provider>
  );
}

function Button({ onOpen }) {
  return (
    <button type="button" className="rp-fab" id="rp-fab" aria-label="Explain these in simpler words" aria-haspopup="dialog"
      onClick={onOpen}>?</button>
  );
}

// The bottom sheet: every card on screen with a tick box. Nothing is typed.
function Sheet({ cards, onClose, onRun }) {
  const [picked, setPicked] = useState(() => new Set());
  const first = useRef(null);
  useEffect(() => {
    first.current?.focus();
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.getElementById("rp-fab")?.focus();   // hand focus back to the "?"
    };
  }, [onClose]);
  // A card can leave the screen while the sheet is open: only ids still listed count.
  const ids = cards.map((c) => c.id).filter((id) => picked.has(id));
  const toggle = (id) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  return (
    <>
      <div className="rp-scrim" onClick={onClose} />
      <section className="rp-sheet" role="dialog" aria-labelledby="rp-title">
        <header>
          <h2 id="rp-title">Which would you like in simpler words?</h2>
          <button type="button" className="rp-x" aria-label="Close" onClick={onClose}>×</button>
        </header>
        <div className="rp-picks">
          {cards.map((c, i) => (
            <label key={c.id} className="rp-pick">
              <input ref={i === 0 ? first : null} type="checkbox" checked={picked.has(c.id)} onChange={() => toggle(c.id)} />
              <span><b>{c.title}</b><small>{c.kind}</small></span>
            </label>
          ))}
        </div>
        <button type="button" className="btn btn-primary btn-lg" disabled={!ids.length} onClick={() => onRun(ids)}>
          {ids.length ? `Rephrase ${ids.length} ${ids.length === 1 ? "card" : "cards"}` : "Rephrase"}
        </button>
      </section>
    </>
  );
}

export function Rephrasable({ id, kind, title, text, alertId = null, children }) {
  const ctx = useContext(Ctx);
  const register = ctx?.register;
  const unregister = ctx?.unregister;
  useEffect(() => { register?.({ id, kind, title, text, alertId }); }, [register, id, kind, title, text, alertId]);
  useEffect(() => () => unregister?.(id), [unregister, id]);
  const r = ctx?.results[id];
  return (
    <>
      {children}
      {r ? <SimplerWords r={r} onHide={() => ctx.hide(id)} onRetry={() => ctx.run([id])} /> : null}
    </>
  );
}

function SimplerWords({ r, onHide, onRetry }) {
  const bad = r.state === "err" || r.state === "off";
  return (
    <div className={`rp-simple${bad ? " bad" : ""}`} role="status" aria-live="polite">
      <div className="rp-tag">
        <span>{bad ? "Couldn't rephrase" : "In simpler words"}</span>
        {r.state !== "loading" ? <button type="button" onClick={onHide}>Hide</button> : null}
      </div>
      {r.state === "loading"
        ? <span className="rp-dots" role="img" aria-label="Rephrasing"><i /><i /><i /></span>
        : <p>{r.text}</p>}
      {r.state === "err" ? <button type="button" className="btn btn-soft" onClick={onRetry}>Try again</button> : null}
    </div>
  );
}
