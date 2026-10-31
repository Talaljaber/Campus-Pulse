import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const tickets = vi.hoisted(() => ({
  list: vi.fn(),
  links: vi.fn(),
  subscribe: vi.fn(),
  off: vi.fn(),
}));
const preds = vi.hoisted(() => ({ byIds: vi.fn(), subscribe: vi.fn(), off: vi.fn() }));
const reqs = vi.hoisted(() => ({ review: vi.fn(), byIds: vi.fn() }));
const svc = vi.hoisted(() => ({ setStatus: vi.fn(), feedback: vi.fn() }));
const inc = vi.hoisted(() => ({ list: vi.fn(), subscribe: vi.fn(), off: vi.fn(), resolve: vi.fn() }));

vi.mock("@/lib/supabase/browser", () => ({ createBrowserSupabase: () => ({}) }));
vi.mock("@/lib/repos/tickets", () => ({
  listTickets: tickets.list,
  listTicketLinks: tickets.links,
  subscribeTickets: tickets.subscribe,
}));
vi.mock("@/lib/repos/predictions", () => ({
  listPredictionsByIds: preds.byIds,
  subscribePredictions: preds.subscribe,
}));
vi.mock("@/lib/repos/requests", () => ({ listReviewQueue: reqs.review, listRequestsByIds: reqs.byIds }));
vi.mock("@/lib/repos/incidents", () => ({ listOpenIncidents: inc.list, subscribeIncidents: inc.subscribe }));
vi.mock("@/lib/staff/service", async (orig) => ({
  ...(await orig<typeof import("@/lib/staff/service")>()),
  setTicketStatus: svc.setStatus,
  sendFeedback: svc.feedback,
}));
vi.mock("@/lib/incidents", async (orig) => ({ ...(await orig<typeof import("@/lib/incidents")>()), resolveIncident: inc.resolve }));

import { useIncidents } from "../useIncidents";
import { useReviewQueue } from "../useReviewQueue";
import { useTicketQueue } from "../useTicketQueue";

const row = (o: Record<string, unknown> = {}) => ({
  id: "t1",
  request_id: "r1",
  incident_id: null,
  office: "it",
  category: "IT Support",
  priority: "medium",
  status: "open",
  provisional: false,
  title: "Wi-Fi",
  body: "",
  sla_due_at: "2026-11-08T12:00:00Z",
  escalated_at: null,
  resolved_at: null,
  created_at: "2026-11-08T08:00:00Z",
  ...o,
});

const fail = (status: number, code: string) => ({ ok: false, status, code, error: "", details: null, waking: false });

beforeEach(() => {
  vi.clearAllMocks();
  tickets.list.mockResolvedValue([row()]);
  tickets.links.mockResolvedValue([]);
  tickets.subscribe.mockReturnValue(tickets.off);
  preds.subscribe.mockReturnValue(preds.off);
  inc.subscribe.mockReturnValue(inc.off);
});

describe("useTicketQueue", () => {
  it("loads, subscribes for the office and unsubscribes on unmount", async () => {
    const { result, unmount } = renderHook(() => useTicketQueue("it"));
    expect(result.current.load).toBe("loading");
    await waitFor(() => expect(result.current.load).toBe("ready"));
    expect(tickets.list).toHaveBeenCalledWith(expect.anything(), "it");
    expect(tickets.subscribe).toHaveBeenCalledWith(expect.anything(), "it", expect.any(Function));
    expect(result.current.tickets).toHaveLength(1);
    unmount();
    expect(tickets.off).toHaveBeenCalledTimes(1);
  });

  it("follows live inserts and updates, and reads the link of a new ticket", async () => {
    tickets.links.mockResolvedValueOnce([]).mockResolvedValueOnce([{ ticket_id: "t2", external_id: "CP-2", external_url: "https://linear.app/x" }]);
    const { result } = renderHook(() => useTicketQueue("it"));
    await waitFor(() => expect(result.current.load).toBe("ready"));
    const push = tickets.subscribe.mock.calls[0]![2] as (r: unknown) => void;
    act(() => push(row({ id: "t2", title: "New" })));
    await waitFor(() => expect(result.current.tickets.find((t) => t.id === "t2")?.link?.id).toBe("CP-2"));
    act(() => push(row({ id: "t1", status: "resolved" })));
    expect(result.current.tickets.find((t) => t.id === "t1")?.status).toBe("resolved");
  });

  it("goes to the error state on a failed read and recovers on reload", async () => {
    tickets.list.mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useTicketQueue(null));
    await waitFor(() => expect(result.current.load).toBe("error"));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.load).toBe("ready"));
  });

  it("changes a status through the API and keeps the office code", async () => {
    svc.setStatus.mockResolvedValue({ ok: true, data: { status: "in_progress", resolved_at: null, escalated_at: null, provisional: false, priority: "medium", sla_due_at: "2026-11-08T12:00:00Z", office: "Maintenance" } });
    const { result } = renderHook(() => useTicketQueue("it"));
    await waitFor(() => expect(result.current.load).toBe("ready"));
    let kind: unknown;
    await act(async () => {
      kind = await result.current.changeStatus("t1", "in_progress");
    });
    expect(kind).toBeNull();
    expect(result.current.tickets[0]).toMatchObject({ status: "in_progress", office: "it" });
    expect(result.current.pending.size).toBe(0);
  });

  it("returns the error kind and leaves the ticket alone on a failed change", async () => {
    svc.setStatus.mockResolvedValue(fail(403, "forbidden"));
    const { result } = renderHook(() => useTicketQueue("it"));
    await waitFor(() => expect(result.current.load).toBe("ready"));
    let kind: unknown;
    await act(async () => {
      kind = await result.current.changeStatus("t1", "closed");
    });
    expect(kind).toBe("forbidden");
    expect(result.current.tickets[0]!.status).toBe("open");
  });
});

describe("useReviewQueue", () => {
  const review = { id: "rv1", prediction_id: "p1", reason: "x", status: "open", created_at: "2026-11-08T09:00:00Z" };
  const prediction = { id: "p1", request_id: "r1", category: "Finance", priority: "medium", flags: ["needs_review"], set_cat: ["Finance", "Registration"], set_pri: ["medium"], explanation: null, core: null, tier: "tier0" };

  beforeEach(() => {
    reqs.review.mockResolvedValue([review]);
    preds.byIds.mockResolvedValue([prediction]);
    reqs.byIds.mockResolvedValue([{ id: "r1", raw_text: "account on hold" }]);
  });

  it("builds the queue from review rows, predictions and requests", async () => {
    const { result } = renderHook(() => useReviewQueue());
    await waitFor(() => expect(result.current.load).toBe("ready"));
    expect(result.current.items[0]).toMatchObject({ predictionId: "p1", text: "account on hold", category: "Finance" });
  });

  it("re-reads the queue (debounced) when a prediction that may need review arrives, and ignores others", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { result } = renderHook(() => useReviewQueue());
      await waitFor(() => expect(result.current.load).toBe("ready"));
      const push = preds.subscribe.mock.calls[0]![1] as (r: unknown) => void;
      push({ flags: ["safety"] });
      push({ flags: ["needs_review"] });
      push({ flags: ["distress"] });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
      });
      expect(reqs.review).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("confirm sends both labels null and removes the item", async () => {
    svc.feedback.mockResolvedValue({ ok: true, data: { ticket: { id: "t9" } } });
    const { result } = renderHook(() => useReviewQueue());
    await waitFor(() => expect(result.current.load).toBe("ready"));
    let out: unknown;
    await act(async () => {
      out = await result.current.confirm("p1");
    });
    expect(svc.feedback).toHaveBeenCalledWith("p1", { category: null, priority: null, note: "" });
    expect(out).toEqual({ ok: true, ticketId: "t9" });
    expect(result.current.items).toHaveLength(0);
  });

  it("keeps the item and reports the kind when the service refuses", async () => {
    svc.feedback.mockResolvedValue(fail(403, "forbidden"));
    const { result } = renderHook(() => useReviewQueue());
    await waitFor(() => expect(result.current.load).toBe("ready"));
    let out: unknown;
    await act(async () => {
      out = await result.current.correct("p1", { category: "Registration", priority: "high", note: "n" });
    });
    expect(out).toEqual({ ok: false, kind: "forbidden" });
    expect(result.current.items).toHaveLength(1);
  });

  it("shows the error state when the first read fails", async () => {
    reqs.review.mockRejectedValueOnce(new Error("rls"));
    const { result } = renderHook(() => useReviewQueue());
    await waitFor(() => expect(result.current.load).toBe("error"));
  });
});

describe("useIncidents", () => {
  const incident = { id: "i1", building_id: "M", category: "IT Support", opened_at: "2026-11-08T09:00:00Z", priority: "high", report_count: 3, status: "open", title: "Wi-Fi" };

  it("loads, follows live changes and removes a resolved incident", async () => {
    inc.list.mockResolvedValue([incident]);
    const { result } = renderHook(() => useIncidents());
    await waitFor(() => expect(result.current.load).toBe("ready"));
    const push = inc.subscribe.mock.calls[0]![1] as (r: unknown) => void;
    act(() => push({ ...incident, report_count: 6 }));
    expect(result.current.rows[0]!.report_count).toBe(6);
    act(() => push({ ...incident, status: "resolved" }));
    expect(result.current.rows).toHaveLength(0);
  });

  it("resolve calls the API, removes the incident and returns the notified count", async () => {
    inc.list.mockResolvedValue([incident]);
    inc.resolve.mockResolvedValue({ ok: true, data: { notified_reporters: 4 } });
    const { result } = renderHook(() => useIncidents());
    await waitFor(() => expect(result.current.load).toBe("ready"));
    let out: unknown;
    await act(async () => {
      out = await result.current.resolve("i1", "fixed");
    });
    expect(inc.resolve).toHaveBeenCalledWith("i1", "fixed");
    expect(out).toEqual({ ok: true, notified: 4 });
    expect(result.current.rows).toHaveLength(0);
  });

  it("keeps the incident when resolving fails", async () => {
    inc.list.mockResolvedValue([incident]);
    inc.resolve.mockResolvedValue(fail(404, "not_found"));
    const { result } = renderHook(() => useIncidents());
    await waitFor(() => expect(result.current.load).toBe("ready"));
    let out: unknown;
    await act(async () => {
      out = await result.current.resolve("i1");
    });
    expect(out).toEqual({ ok: false, kind: "notFound" });
    expect(result.current.rows).toHaveLength(1);
  });
});
