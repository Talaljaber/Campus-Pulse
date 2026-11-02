import { afterEach, describe, expect, it, vi } from "vitest";
import { failFromNetwork, failFromResponse } from "@/lib/ai/result";
import { fetchReviews, forwardErrorKind, forwardReview, forwardTicket, staffErrorKind } from "../service";
import { applyForward, type TicketView } from "../tickets";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  const fn = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("review and ticket forward calls", () => {
  it("reads reviews through the proxy with the status in the query", async () => {
    const fn = stubFetch(200, []);
    expect(await fetchReviews("corrected")).toEqual({ ok: true, data: [] });
    expect(fn.mock.calls[0]![0]).toBe("/api/ai/reviews?status=corrected");
  });

  it("posts {office, note} and turns a blank note into null", async () => {
    const fn = stubFetch(200, { ok: 1 });
    await forwardReview("r/1", "it", "  ");
    const [url, init] = fn.mock.calls[0]! as unknown as [string, RequestInit];
    expect(url).toBe("/api/ai/reviews/r%2F1/forward");
    expect(JSON.parse(init.body as string)).toEqual({ office: "it", note: null });
    await forwardTicket("t1", "facilities", " Check the router ");
    const [url2, init2] = fn.mock.calls[1]! as unknown as [string, RequestInit];
    expect(url2).toBe("/api/ai/tickets/t1/forward");
    expect(JSON.parse(init2.body as string)).toEqual({ office: "facilities", note: "Check the router" });
  });

  it("returns the 403 as a failure the page can word", async () => {
    stubFetch(403, { error: { code: "forbidden", message: "not yours", details: null } });
    const res = await forwardReview("r1", "finance", "");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(forwardErrorKind(res)).toBe("notYours");
  });
});

describe("forwardErrorKind", () => {
  it("words a 403 as not-yours and leaves the other kinds as staffErrorKind has them", () => {
    expect(forwardErrorKind(failFromResponse(403, { error: { code: "forbidden", message: "x", details: null } }))).toBe("notYours");
    expect(staffErrorKind(failFromResponse(403, { error: { code: "forbidden", message: "x", details: null } }))).toBe("forbidden");
    expect(forwardErrorKind(failFromResponse(404, { error: { code: "not_found", message: "x", details: null } }))).toBe("notFound");
    expect(forwardErrorKind(failFromResponse(401, { error: { code: "unauthenticated", message: "x", details: null } }))).toBe("session");
    expect(forwardErrorKind(failFromNetwork(true))).toBe("waking");
  });
});

describe("applyForward", () => {
  it("moves the row to the picked office code and the category that follows it, keeping status and SLA", () => {
    const row = { id: "t", office: "it", category: "IT Support", status: "new", priority: "high" } as unknown as TicketView;
    const out = { status: "new", resolved_at: null, escalated_at: null, provisional: false, priority: "high", sla_due_at: "2026-11-09T10:00:00Z" };
    // The API may word the office ("Maintenance"); the row keeps the code the staff member picked.
    expect(applyForward(row, { ...out, category: "Facilities" }, "facilities")).toMatchObject({
      office: "facilities",
      category: "Facilities",
      status: "new",
      sla_due_at: "2026-11-09T10:00:00Z",
    });
  });
});
