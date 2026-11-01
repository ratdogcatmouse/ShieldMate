import { beforeEach, describe, expect, it } from "vitest";
import { getLastDrill, getLang, getOwnerPin, getPlayer, syncResetId } from "./session.js";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

describe("syncResetId: a demo reset starts this device afresh", () => {
  it("remembers the first id without asking for a reload", () => {
    expect(syncResetId("aaaa")).toBe(false);
    expect(syncResetId("aaaa")).toBe(false);
  });

  it("clears drill players, the last drill, the owner PIN and seen marks when the id changes", () => {
    syncResetId("aaaa");
    localStorage.setItem("sm.player.1234.1", "7");
    localStorage.setItem("sm.last_drill", "1234");
    localStorage.setItem("sm.lang", "kn");
    sessionStorage.setItem("sm.owner_pin", "1234");
    sessionStorage.setItem("sm.seen.alert.3", "1");
    sessionStorage.setItem("sm.backstage_token", "tok");

    expect(syncResetId("bbbb")).toBe(true);
    expect(getPlayer("1234", 1)).toBeNull();
    expect(getLastDrill()).toBeNull();
    expect(getOwnerPin()).toBeNull();
    expect(sessionStorage.getItem("sm.seen.alert.3")).toBeNull();
    expect(getLang()).toBe("kn");
    expect(sessionStorage.getItem("sm.backstage_token")).toBe("tok");
  });

  it("ignores a missing id (an older backend)", () => {
    localStorage.setItem("sm.last_drill", "1234");
    expect(syncResetId(undefined)).toBe(false);
    expect(syncResetId("")).toBe(false);
    expect(getLastDrill()).toBe("1234");
  });
});
