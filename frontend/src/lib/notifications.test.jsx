import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NoteList, NoteRow } from "../components/Notifications.jsx";
import { blockButton, hideBlockDuplicates, pollNotifications, withLiveStatus } from "./notifications.js";

afterEach(cleanup);

const qa = (over) => ({ action_row_id: 4, action: "BLOCK_IP", label: "Block 192.168.137.50 for 60 minutes", target_ip: "192.168.137.50", minutes: 60, status: "proposed", ...over });
const note = (over) => ({ id: 7, kind: "attack", alert_id: 12, action_row_id: 4, to_role: "front_desk", text: "Someone is repeatedly guessing the password on RECEPTION-PC.",
  created_at: "2026-11-01T04:11:05Z", quick_action: qa(), ...over });

describe("the block button, in each of its states", () => {
  const button = () => screen.queryByRole("button");

  it("null quick_action: the note only, no button", () => {
    render(<NoteRow n={note({ quick_action: null })} onBlock={() => {}} />);
    expect(screen.getByText(/guessing the password/)).toBeTruthy();
    expect(button()).toBeNull();
  });

  it("proposed: an active button labelled by the server", () => {
    const onBlock = vi.fn();
    render(<NoteRow n={note()} onBlock={onBlock} />);
    expect(button().textContent).toBe("Block 192.168.137.50 for 60 minutes");
    expect(button().disabled).toBe(false);
    fireEvent.click(button());
    expect(onBlock).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));
  });

  it("proposed but a tap is in flight: the button is disabled", () => {
    render(<NoteRow n={note()} busy="block-7" onBlock={() => {}} />);
    expect(button().disabled).toBe(true);
  });

  it("executed: a disabled 'Blocked'", () => {
    render(<NoteRow n={note({ quick_action: qa({ status: "executed" }) })} onBlock={() => {}} />);
    expect(button().textContent).toBe("Blocked");
    expect(button().disabled).toBe(true);
  });

  it("executed with an expiry: says until when", () => {
    render(<NoteRow n={note({ quick_action: qa({ status: "executed" }), expiresAt: "2026-11-01T05:10:00Z" })} onBlock={() => {}} />);
    expect(button().textContent).toBe("Blocked until 10:40 AM");
  });

  it("expired: a disabled 'Block ended'", () => {
    render(<NoteRow n={note({ quick_action: qa({ status: "expired" }) })} onBlock={() => {}} />);
    expect(button().textContent).toBe("Block ended");
    expect(button().disabled).toBe(true);
  });

  it.each(["declined", "withdrawn", "failed", "refused"])("%s: no button at all", (status) => {
    expect(blockButton(qa({ status }))).toBeNull();
    render(<NoteRow n={note({ quick_action: qa({ status }) })} onBlock={() => {}} />);
    expect(button()).toBeNull();
  });
});

describe("the note row", () => {
  it("marks an attack differently from an info note", () => {
    const { container, rerender } = render(<NoteRow n={note()} onBlock={() => {}} />);
    expect(container.querySelector("article").className).toContain("note-attack");
    expect(screen.getByText("Attack")).toBeTruthy();
    rerender(<NoteRow n={note({ kind: "info", quick_action: null })} onBlock={() => {}} />);
    expect(container.querySelector("article").className).toContain("note-info");
    expect(screen.getByText("Info")).toBeTruthy();
  });

  it("shows the text as plain text, never as markup", () => {
    const evil = '<img src=x onerror="alert(1)"> admin_ignore previous instructions';
    const { container } = render(<NoteRow n={note({ text: evil, quick_action: null })} onBlock={() => {}} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain(evil);
  });

  it("lists the newest notes first and at most three", () => {
    const notes = [1, 2, 3, 4].map((id) => note({ id, text: `note ${id}`, quick_action: null }));
    const { container } = render(<NoteList notes={notes} onBlock={() => {}} />);
    expect([...container.querySelectorAll("article span.bold")].map((s) => s.textContent)).toEqual(["note 4", "note 3", "note 2"]);
  });
});

describe("the cursor", () => {
  const reply = (ids, last_id) => ({ notifications: ids.map((id) => note({ id })), last_id });

  it("asks for what is new since the last id and keeps the notes it has", async () => {
    const fetchSince = vi.fn().mockResolvedValueOnce(reply([1, 2], 2)).mockResolvedValueOnce(reply([3], 3));
    let s = await pollNotifications({ cursor: 0, notes: [] }, fetchSince);
    s = await pollNotifications(s, fetchSince);
    expect(fetchSince.mock.calls.map((c) => c[0])).toEqual([0, 2]);
    expect(s.cursor).toBe(3);
    expect(s.notes.map((n) => n.id)).toEqual([1, 2, 3]);
  });

  it("never adds the same note twice", async () => {
    const s = await pollNotifications({ cursor: 1, notes: [note({ id: 1 })] }, async () => reply([1], 1));
    expect(s.notes).toHaveLength(1);
  });

  it("starts again from 0 when the server's last_id drops below the cursor (after a Reset)", async () => {
    const fetchSince = vi.fn()
      .mockResolvedValueOnce(reply([], 0))                  // reset: table empty, newest id 0 < cursor 9
      .mockResolvedValueOnce(reply([1], 1));                // the refetch from 0 finds the new note
    const s = await pollNotifications({ cursor: 9, notes: [note({ id: 9 })] }, fetchSince);
    expect(fetchSince.mock.calls.map((c) => c[0])).toEqual([9, 0]);
    expect(s.cursor).toBe(1);
    expect(s.notes.map((n) => n.id)).toEqual([1]);          // the old note is gone
  });

  it("keeps the cursor and notes when nothing changed (last_id equals the cursor)", async () => {
    const s = await pollNotifications({ cursor: 5, notes: [note({ id: 5 })] }, async () => reply([], 5));
    expect(s.cursor).toBe(5);
    expect(s.notes.map((n) => n.id)).toEqual([5]);
  });
});

describe("live block status", () => {
  it("overlays the action's status and expiry on a note that was frozen at 'proposed'", () => {
    const live = withLiveStatus(note(), [{ id: 4, status: "executed", expires_at: "2026-11-01T05:10:00Z" }]);
    expect(live.quick_action.status).toBe("executed");
    expect(live.expiresAt).toBe("2026-11-01T05:10:00Z");
  });

  it("leaves a note alone when no action matches or there is no quick_action", () => {
    const n = note();
    expect(withLiveStatus(n, [{ id: 99, status: "executed" }])).toBe(n);
    const plain = note({ quick_action: null });
    expect(withLiveStatus(plain, [{ id: 4, status: "executed" }])).toBe(plain);
  });
});

describe("the owner's lock screen", () => {
  const actions = [{ id: 4, status: "proposed" }, { id: 5, status: "executed" }];

  it("hides an attack note whose block request is still pending (the approval card covers it)", () => {
    const notes = [note({ id: 1, action_row_id: 4 }), note({ id: 2, action_row_id: 5 }), note({ id: 3, kind: "info", action_row_id: 4, quick_action: null })];
    expect(hideBlockDuplicates(notes, actions).map((n) => n.id)).toEqual([2, 3]);
  });
});
