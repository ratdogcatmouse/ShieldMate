// "Explain in simpler words" for a card on screen. There is no typed question: the picker sends a
// fixed instruction plus the card's own headline and body (the app's filled lesson text, never
// log_fields) to POST /interpreter/chat, once per ticked card. Gated by the server flag
// AI_INTERPRETER: with it off the route answers not_enabled.
import * as api from "./api.js";

export const QUESTION_MAX = 500; // InterpreterRequest.question
const PREFIX = "Explain this in simpler words: ";

export const OFF_TEXT = "AI help isn't enabled here.";
export const ERR_TEXT = "Couldn't rephrase this right now. The wording on the card above is still correct.";

const squash = (s) => String(s ?? "").replace(/\s+/g, " ").trim();

// The one question sent for a card: instruction + headline + body, cut to the server's 500-char cap.
export function buildQuestion(title, text) {
  const q = PREFIX + [squash(title), squash(text)].filter(Boolean).join(" ");
  return q.length <= QUESTION_MAX ? q : `${q.slice(0, QUESTION_MAX - 1)}…`;
}

// -> { state: "done" | "err" | "off", text }. Never throws: a failed card shows on its own card.
// source "fallback" means the agent was unreachable and the server sent generic guidance
// (not this card's words), so it is shown as a failure rather than as a rephrasing.
export async function explainCard(card, { role, lang }) {
  try {
    const r = await api.interpret({
      question: buildQuestion(card.title, card.text),
      role,
      lang,
      alert_id: card.alertId ?? null,
    });
    if (r.source === "fallback" || !String(r.answer || "").trim()) return { state: "err", text: ERR_TEXT };
    return { state: "done", text: r.answer };
  } catch (e) {
    if (e?.error === "not_enabled") return { state: "off", text: OFF_TEXT };
    return { state: "err", text: ERR_TEXT };
  }
}
