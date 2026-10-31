import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const off = vi.fn();
let push: (row: { kind: string; payload: unknown }) => void = () => {};
const subscribe = vi.fn((_sb: unknown, _alias: string, cb: typeof push) => {
  push = cb;
  return off;
});

vi.mock("@/lib/repos/notifications", () => ({ subscribeNotifications: (...a: Parameters<typeof subscribe>) => subscribe(...a) }));
vi.mock("@/lib/supabase/browser", () => ({ createBrowserSupabase: () => ({}) }));

import { useNotifications } from "../useNotifications";

beforeEach(() => {
  off.mockClear();
  subscribe.mockClear();
});

describe("useNotifications", () => {
  it("subscribes for the alias, reports notices, and unsubscribes on unmount", () => {
    const onNotice = vi.fn();
    const { unmount } = renderHook(() => useNotifications("talal", onNotice));
    expect(subscribe).toHaveBeenCalledWith(expect.anything(), "talal", expect.any(Function));
    push({ kind: "ticket_status", payload: { status: "resolved", title: "Wi-Fi" } });
    expect(onNotice).toHaveBeenCalledWith({ type: "ticket_status", title: "Wi-Fi", status: "resolved" });
    unmount();
    expect(off).toHaveBeenCalledTimes(1);
  });

  it("does nothing without an alias", () => {
    renderHook(() => useNotifications(null, vi.fn()));
    expect(subscribe).not.toHaveBeenCalled();
  });
});
