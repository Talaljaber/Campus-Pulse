import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  requests: vi.fn(),
  subRequests: vi.fn(),
  incidents: vi.fn(),
  subIncidents: vi.fn(),
  outbox: vi.fn(),
  subOutbox: vi.fn(),
  latest: vi.fn(),
  subPredictions: vi.fn(),
  resolve: vi.fn(),
  off: vi.fn(),
}));

vi.mock("@/lib/supabase/browser", () => ({ createBrowserSupabase: () => ({}) }));
vi.mock("@/lib/repos/requests", () => ({ listRequestsWithLocation: m.requests, subscribeRequestsWithLocation: m.subRequests }));
vi.mock("@/lib/repos/incidents", () => ({ listOpenIncidents: m.incidents, subscribeIncidents: m.subIncidents }));
vi.mock("@/lib/repos/outbox", () => ({ listOutbox: m.outbox, subscribeOutbox: m.subOutbox }));
vi.mock("@/lib/repos/predictions", () => ({ listLatestPredictions: m.latest, subscribePredictions: m.subPredictions }));
vi.mock("@/lib/incidents", async (orig) => ({ ...(await orig<typeof import("@/lib/incidents")>()), resolveIncident: m.resolve }));

import { dotsOf, openIncidents } from "@/lib/pulse/view";
import { FIXTURE_BUILDINGS } from "@/components/pulse/map/campus";
import { usePulse } from "../usePulse";

const request = { id: "r1", alias: "a", building_id: "M", room: null, status: "decided", simulated: false, created_at: "2026-11-08T09:00:00Z" };
const incident = { id: "i1", building_id: "M", category: "IT Support", created_at: "", office: "it", opened_at: "2026-11-08T09:10:00Z", priority: "high", report_count: 3, resolved_at: null, status: "open", title: "Wi-Fi" };

const pushOf = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls[0]![1] as (row: unknown) => void;

beforeEach(() => {
  vi.clearAllMocks();
  m.requests.mockResolvedValue([request]);
  m.incidents.mockResolvedValue([incident]);
  m.outbox.mockResolvedValue([]);
  m.latest.mockResolvedValue([{ id: "p1", request_id: "r1", category: "IT Support", priority: "high", created_at: "" }]);
  for (const s of [m.subRequests, m.subIncidents, m.subOutbox, m.subPredictions]) s.mockReturnValue(m.off);
});

describe("usePulse", () => {
  it("reads one snapshot and subscribes to the four tables, then unsubscribes all of them", async () => {
    const { result, unmount } = renderHook(() => usePulse());
    expect(result.current.load).toBe("loading");
    await waitFor(() => expect(result.current.load).toBe("ready"));
    expect(m.outbox).toHaveBeenCalledWith(expect.anything(), { kind: "broadcast", limit: 20 });
    expect(m.latest).toHaveBeenCalledWith(expect.anything(), ["r1"]);
    expect(dotsOf(result.current.state, FIXTURE_BUILDINGS)).toHaveLength(1);
    expect(openIncidents(result.current.state)).toHaveLength(1);
    expect(result.current.state.feed.length).toBe(2);
    unmount();
    expect(m.off).toHaveBeenCalledTimes(4);
  });

  it("shows a live request as a dot once its prediction arrives, and a bump as a feed line", async () => {
    const { result } = renderHook(() => usePulse());
    await waitFor(() => expect(result.current.load).toBe("ready"));
    act(() => pushOf(m.subRequests)({ ...request, id: "r2", created_at: "2026-11-08T09:30:00Z" }));
    expect(dotsOf(result.current.state, FIXTURE_BUILDINGS)).toHaveLength(1);
    act(() => pushOf(m.subPredictions)({ request_id: "r2", category: "Finance", priority: "low" }));
    expect(dotsOf(result.current.state, FIXTURE_BUILDINGS)).toHaveLength(2);

    act(() => pushOf(m.subIncidents)({ ...incident, report_count: 6 }));
    expect(result.current.state.feed.find((e) => e.kind === "incident_bump")).toMatchObject({ count: 6 });
  });

  it("goes to the error state and recovers on reload", async () => {
    m.requests.mockRejectedValueOnce(new Error("rls"));
    const { result } = renderHook(() => usePulse());
    await waitFor(() => expect(result.current.load).toBe("error"));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.load).toBe("ready"));
  });

  it("resolve removes the incident and reports the notified count", async () => {
    m.resolve.mockResolvedValue({ ok: true, data: { notified_reporters: 4, incident: { id: "i1", building: "M", category: "IT Support", title: "Wi-Fi", priority: "high", report_count: 3, status: "resolved", opened_at: "2026-11-08T09:10:00Z", resolved_at: "2026-11-08T10:00:00Z" } } });
    const { result } = renderHook(() => usePulse());
    await waitFor(() => expect(result.current.load).toBe("ready"));
    let out: unknown;
    await act(async () => {
      out = await result.current.resolve("i1", "fixed");
    });
    expect(m.resolve).toHaveBeenCalledWith("i1", "fixed");
    expect(out).toEqual({ ok: true, notified: 4 });
    expect(openIncidents(result.current.state)).toHaveLength(0);
    expect(result.current.state.feed.some((e) => e.kind === "resolved")).toBe(true);
  });

  it("keeps the incident when resolving is refused", async () => {
    m.resolve.mockResolvedValue({ ok: false, status: 403, code: "forbidden", error: "", details: null, waking: false });
    const { result } = renderHook(() => usePulse());
    await waitFor(() => expect(result.current.load).toBe("ready"));
    let out: unknown;
    await act(async () => {
      out = await result.current.resolve("i1");
    });
    expect(out).toEqual({ ok: false, kind: "forbidden" });
    expect(openIncidents(result.current.state)).toHaveLength(1);
  });
});
