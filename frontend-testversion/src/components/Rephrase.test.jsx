import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api.js", () => ({ interpret: vi.fn() }));
import * as api from "../lib/api.js";
import { Rephrasable, RephraseProvider } from "./Rephrase.jsx";

beforeEach(() => { api.interpret.mockReset(); });
afterEach(cleanup);

function Screen({ cards = ["a", "b"] }) {
  return (
    <RephraseProvider role="front_desk" lang="en">
      <h1>Screen</h1>
      {cards.includes("a") ? (
        <Rephrasable id="alert-1" kind="Alert" title="Password guessing" text="18 tries." alertId={1}>
          <article>Original alert wording</article>
        </Rephrasable>
      ) : null}
      {cards.includes("b") ? (
        <Rephrasable id="action-7" kind="Decision" title="Block the attacker?" text="60 minutes.">
          <article>Original decision wording</article>
        </Rephrasable>
      ) : null}
    </RephraseProvider>
  );
}

const fab = () => screen.queryByRole("button", { name: /simpler words/i });
const open = async () => { fireEvent.click(fab()); return screen.findByRole("dialog"); };

describe("the ? button", () => {
  it("is not there when no card is on screen", () => {
    render(<Screen cards={[]} />);
    expect(fab()).toBeNull();
  });

  it("appears when a card is on screen and goes when the last one leaves", async () => {
    const { rerender } = render(<Screen cards={["a"]} />);
    await waitFor(() => expect(fab()).not.toBeNull());
    rerender(<Screen cards={[]} />);
    await waitFor(() => expect(fab()).toBeNull());
  });
});

describe("the picker", () => {
  it("lists every card on screen, with nothing to type", async () => {
    render(<Screen />);
    await waitFor(() => expect(fab()).not.toBeNull());
    const dialog = await open();
    expect(dialog.textContent).toContain("Password guessing");
    expect(dialog.textContent).toContain("Block the attacker?");
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("Rephrase stays disabled until a card is ticked, and counts them", async () => {
    render(<Screen />);
    await waitFor(() => expect(fab()).not.toBeNull());
    await open();
    const go = screen.getByRole("button", { name: "Rephrase" });
    expect(go.disabled).toBe(true);
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.getByRole("button", { name: "Rephrase 1 card" }).disabled).toBe(false);
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    expect(screen.getByRole("button", { name: "Rephrase 2 cards" })).toBeTruthy();
  });

  it("Escape closes it", async () => {
    render(<Screen />);
    await waitFor(() => expect(fab()).not.toBeNull());
    await open();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("rephrasing", () => {
  it("shows the answer under only the ticked card, and leaves the original wording alone", async () => {
    api.interpret.mockResolvedValue({ answer: "Someone keeps trying keys on the door.", source: "ai" });
    render(<Screen />);
    await waitFor(() => expect(fab()).not.toBeNull());
    await open();
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Rephrase 1 card" }));
    expect(await screen.findByText("Someone keeps trying keys on the door.")).toBeTruthy();
    expect(screen.getAllByText("In simpler words")).toHaveLength(1);
    expect(screen.getByText("Original alert wording")).toBeTruthy();
    expect(api.interpret).toHaveBeenCalledTimes(1);
    expect(api.interpret.mock.calls[0][0]).toMatchObject({ role: "front_desk", lang: "en", alert_id: 1 });
  });

  it("one request per ticked card", async () => {
    api.interpret.mockResolvedValue({ answer: "ok", source: "ai" });
    render(<Screen />);
    await waitFor(() => expect(fab()).not.toBeNull());
    await open();
    screen.getAllByRole("checkbox").forEach((c) => fireEvent.click(c));
    fireEvent.click(screen.getByRole("button", { name: "Rephrase 2 cards" }));
    await waitFor(() => expect(screen.getAllByText("In simpler words")).toHaveLength(2));
    expect(api.interpret).toHaveBeenCalledTimes(2);
  });

  it("Hide removes the block", async () => {
    api.interpret.mockResolvedValue({ answer: "Simple.", source: "ai" });
    render(<Screen cards={["a"]} />);
    await waitFor(() => expect(fab()).not.toBeNull());
    await open();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Rephrase 1 card" }));
    await screen.findByText("Simple.");
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByText("Simple.")).toBeNull();
  });

  it("renders the answer as plain text, never as HTML", async () => {
    api.interpret.mockResolvedValue({ answer: "<img src=x onerror=alert(1)> <b>hi</b>", source: "ai" });
    const { container } = render(<Screen cards={["a"]} />);
    await waitFor(() => expect(fab()).not.toBeNull());
    await open();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Rephrase 1 card" }));
    await screen.findByText(/<b>hi<\/b>/);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".rp-simple b")).toBeNull();
  });

  it("a server failure shows on that card with Try again, which asks again", async () => {
    api.interpret.mockRejectedValueOnce({ status: 500, error: "server_error" });
    api.interpret.mockResolvedValueOnce({ answer: "Second time worked.", source: "ai" });
    render(<Screen cards={["a"]} />);
    await waitFor(() => expect(fab()).not.toBeNull());
    await open();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Rephrase 1 card" }));
    expect(await screen.findByText("Couldn't rephrase")).toBeTruthy();
    expect(screen.getByText("Original alert wording")).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Try again" })); });
    expect(await screen.findByText("Second time worked.")).toBeTruthy();
  });

  it("not_enabled says so and takes the ? away", async () => {
    api.interpret.mockImplementation(() => Promise.reject({ status: 404, error: "not_enabled" }));
    render(<Screen cards={["a"]} />);
    await waitFor(() => expect(fab()).not.toBeNull());
    await open();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Rephrase 1 card" }));
    expect(await screen.findByText("AI help isn't enabled here.")).toBeTruthy();
    expect(fab()).toBeNull();
  });
});
