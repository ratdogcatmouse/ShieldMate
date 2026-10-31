import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api.js", () => ({ interpret: vi.fn() }));
import * as api from "./api.js";
import { buildQuestion, ERR_TEXT, explainCard, OFF_TEXT, QUESTION_MAX } from "./rephrase.js";

beforeEach(() => { api.interpret.mockReset(); });

describe("buildQuestion", () => {
  it("is a fixed instruction plus the card's headline and body", () => {
    expect(buildQuestion("Someone is guessing passwords.", "18 tries in 5 minutes.")).toBe(
      "Explain this in simpler words: Someone is guessing passwords. 18 tries in 5 minutes.",
    );
  });

  it("collapses whitespace and skips an empty body", () => {
    expect(buildQuestion("  Backup \n is old ", "")).toBe("Explain this in simpler words: Backup is old");
  });

  it("never exceeds the server's 500-character limit", () => {
    const q = buildQuestion("h".repeat(300), "b".repeat(900));
    expect(q.length).toBeLessThanOrEqual(QUESTION_MAX);
    expect(q.endsWith("…")).toBe(true);
  });
});

describe("explainCard", () => {
  const card = { title: "Block the attacker?", text: "18+ wrong passwords.", alertId: 12 };
  const who = { role: "owner", lang: "en" };

  it("sends the question, role, lang and alert id, and returns the agent's answer", async () => {
    api.interpret.mockResolvedValue({ answer: "Shut the door on them.", source: "ai" });
    expect(await explainCard(card, who)).toEqual({ state: "done", text: "Shut the door on them." });
    expect(api.interpret).toHaveBeenCalledWith({
      question: "Explain this in simpler words: Block the attacker? 18+ wrong passwords.",
      role: "owner", lang: "en", alert_id: 12,
    });
  });

  it("sends alert_id null for a card with no alert", async () => {
    api.interpret.mockResolvedValue({ answer: "ok", source: "ai" });
    await explainCard({ title: "t", text: "x" }, who);
    expect(api.interpret.mock.calls[0][0].alert_id).toBeNull();
  });

  it("a fallback answer is generic guidance, not this card's words: shown as a failure", async () => {
    api.interpret.mockResolvedValue({ answer: "The agent isn't reachable right now...", source: "fallback" });
    expect(await explainCard(card, who)).toEqual({ state: "err", text: ERR_TEXT });
  });

  it("an empty answer is a failure", async () => {
    api.interpret.mockResolvedValue({ answer: "  ", source: "ai" });
    expect((await explainCard(card, who)).state).toBe("err");
  });

  it("not_enabled (flag off) says so", async () => {
    api.interpret.mockImplementation(() => Promise.reject({ status: 404, error: "not_enabled" }));
    expect(await explainCard(card, who)).toEqual({ state: "off", text: OFF_TEXT });
  });

  it("a network or server error never throws", async () => {
    api.interpret.mockImplementation(() => Promise.reject({ status: 0, error: "network" }));
    expect(await explainCard(card, who)).toEqual({ state: "err", text: ERR_TEXT });
  });
});
