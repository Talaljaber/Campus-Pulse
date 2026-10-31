import { describe, expect, it, vi } from "vitest";
import {
  listFlaggedPredictions,
  listLatestPredictions,
  listPredictionsByIds,
  listPredictionsForRequest,
  listRequestsByIds,
  listTickets,
  subscribePredictions,
  subscribeTickets,
} from "@/lib/repos";
import type { Sb } from "@/lib/supabase/types";

type Call = [method: string, args: unknown[]];

function fakeSb(result: { data: unknown[] | null; error: { message: string } | null } = { data: [], error: null }) {
  const calls: Record<string, Call[]> = {};
  const handlers: Array<{ opts: Record<string, unknown>; cb: (p: { new: unknown }) => void }> = [];
  const sb = {
    from(table: string) {
      const log: Call[] = (calls[table] = []);
      const builder: unknown = new Proxy(
        {},
        {
          get(_t, prop: string) {
            if (prop === "then") return (res: (v: unknown) => void) => res(result);
            return (...args: unknown[]) => {
              log.push([prop, args]);
              return builder;
            };
          },
        },
      );
      return builder;
    },
    channel() {
      const ch = {
        on(_type: string, opts: Record<string, unknown>, cb: (p: { new: unknown }) => void) {
          handlers.push({ opts, cb });
          return ch;
        },
        subscribe: vi.fn(() => ch),
      };
      return ch;
    },
    removeChannel: vi.fn(() => Promise.resolve("ok")),
  };
  return { sb: sb as unknown as Sb, calls, handlers };
}

const has = (calls: Call[], method: string, ...args: unknown[]) =>
  calls.some(([m, a]) => m === method && JSON.stringify(a) === JSON.stringify(args));

describe("staff reads", () => {
  it("listTickets filters by office, or reads everything RLS allows for null", async () => {
    const a = fakeSb();
    await listTickets(a.sb, "it");
    expect(has(a.calls.tickets!, "eq", "office", "it")).toBe(true);
    const b = fakeSb();
    await listTickets(b.sb, null);
    expect(b.calls.tickets!.some(([m]) => m === "eq")).toBe(false);
  });

  it("skips the round trip for an empty id list", async () => {
    const f = fakeSb();
    expect(await listPredictionsByIds(f.sb, [])).toEqual([]);
    expect(await listRequestsByIds(f.sb, [])).toEqual([]);
    expect(await listLatestPredictions(f.sb, [])).toEqual([]);
    expect(Object.keys(f.calls)).toEqual([]);
  });

  it("reads predictions by id and by request, newest first", async () => {
    const f = fakeSb();
    await listPredictionsByIds(f.sb, ["p1"]);
    expect(has(f.calls.predictions!, "in", "id", ["p1"])).toBe(true);
    const g = fakeSb();
    await listPredictionsForRequest(g.sb, "r1");
    expect(has(g.calls.predictions!, "eq", "request_id", "r1")).toBe(true);
    expect(g.calls.predictions!.some(([m, a]) => m === "order" && a[0] === "created_at")).toBe(true);
  });

  it("keeps only the newest prediction of each request for map dots", async () => {
    const f = fakeSb({
      data: [
        { id: "p2", request_id: "r1", category: "Finance", priority: "high", created_at: "2" },
        { id: "p1", request_id: "r1", category: "IT Support", priority: "low", created_at: "1" },
        { id: "p3", request_id: "r2", category: "IT Support", priority: "low", created_at: "1" },
      ],
      error: null,
    });
    const rows = await listLatestPredictions(f.sb, ["r1", "r2"]);
    expect(rows.map((r) => r.id)).toEqual(["p2", "p3"]);
  });

  it("filters flagged predictions with an array overlap", async () => {
    const f = fakeSb();
    await listFlaggedPredictions(f.sb, ["injection_attempt"], 10);
    expect(has(f.calls.predictions!, "overlaps", "flags", ["injection_attempt"])).toBe(true);
    expect(has(f.calls.predictions!, "limit", 10)).toBe(true);
  });
});

describe("staff subscriptions", () => {
  it("subscribeTickets filters by office, and not at all for an admin", () => {
    const a = fakeSb();
    subscribeTickets(a.sb, "it", () => {});
    expect(a.handlers.every((h) => h.opts.filter === "office=eq.it")).toBe(true);
    const b = fakeSb();
    subscribeTickets(b.sb, null, () => {});
    expect(b.handlers.every((h) => !("filter" in h.opts))).toBe(true);
  });

  it("subscribePredictions reports inserts only", () => {
    const f = fakeSb();
    const cb = vi.fn();
    subscribePredictions(f.sb, cb);
    const insert = f.handlers.find((h) => h.opts.event === "INSERT")!;
    const update = f.handlers.find((h) => h.opts.event === "UPDATE")!;
    insert.cb({ new: { id: "p1" } });
    update.cb({ new: { id: "p2" } });
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith({ id: "p1" });
  });
});
