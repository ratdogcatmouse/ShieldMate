import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Landing from "./Landing.jsx";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// One test, because the landing is shown once per page load (module state) and tests share it.
describe("Landing", () => {
  it("shows the welcome for 3 seconds, then the roles screen, and only once", () => {
    vi.useFakeTimers();
    render(<Landing><p>Roles</p></Landing>);
    expect(screen.getByText("Sunrise Clinic Security")).toBeTruthy();
    expect(screen.queryByText("Roles")).toBeNull();

    act(() => vi.advanceTimersByTime(2999));
    expect(screen.queryByText("Roles")).toBeNull();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByText("Roles")).toBeTruthy();
    expect(screen.queryByText("Sunrise Clinic Security")).toBeNull();

    // Coming back to "/" later (Switch person) goes straight to the roles.
    cleanup();
    render(<Landing><p>Roles</p></Landing>);
    expect(screen.getByText("Roles")).toBeTruthy();
  });
});
