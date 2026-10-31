import { describe, expect, it, vi } from "vitest";
import {
  listMyPredictions,
  listMyRequests,
  listNotifications,
  listOfficeTickets,
  listOpenIncidents,
  listOutbox,
  listRequestsWithLocation,
  listReviewQueue,
  subscribeIncidents,
  subscribeNotifications,
  subscribeRequestsWithLocation,
  subscribeTickets,
} from "@/lib/repos";
import type { Sb } from "@/lib/supabase/types";

type Call = [method: string, args: unknown[]];

/** A chainable stand-in for the Supabase query builder: records calls, resolves to `result` when awaited. */
function fakeSb(result: { data: unknown[] | null; error: { message: string } | null } = { data: [], error: null }) {
  const calls: Record<string, Call[]> = {};
  const handlers: Array<{ opts: Record<string, unknown>; cb: (p: { new: unknown }) => void }> = [];
  const removed: unknown[] = [];
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
    channel(name: string) {
      const ch = {
        name,
        on(_type: string, opts: Record<string, unknown>, cb: (p: { new: unknown }) => void) {
          handlers.push({ opts, cb });
          return ch;
        },
        subscribe: vi.fn(() => ch),
      };
      return ch;
    },
    removeChannel: (ch: unknown) => {
      removed.push(ch);
      return Promise.resolve("ok");
    },
  };
  return { sb: sb as unknown as Sb, calls, handlers, removed };
}

const has = (calls: Call[], method: string, ...args: unknown[]) =>
  calls.some(([m, a]) => m === method && JSON.stringify(a) === JSON.stringify(args));

describe("reads", () => {
  it("listOfficeTickets filters by office and orders by SLA", async () => {
    const f = fakeSb({ data: [{ id: "t1" }], error: null });
    expect(await listOfficeTickets(f.sb, "it")).toEqual([{ id: "t1" }]);
    expect(has(f.calls.tickets!, "eq", "office", "it")).toBe(true);
    expect(f.calls.tickets!.some(([m, a]) => m === "order" && a[0] === "sla_due_at")).toBe(true);
  });

  it("listMyPredictions reads the student view, never the predictions table", async () => {
    const f = fakeSb();
    await listMyPredictions(f.sb, "r1");
    expect(Object.keys(f.calls)).toEqual(["predictions_student_v"]);
    expect(has(f.calls.predictions_student_v!, "eq", "request_id", "r1")).toBe(true);
  });

  it("listMyRequests, listOpenIncidents, listReviewQueue and listOutbox use the expected tables and filters", async () => {
    const f = fakeSb();
    await listMyRequests(f.sb);
    await listOpenIncidents(f.sb);
    await listReviewQueue(f.sb);
    await listOutbox(f.sb, { kind: "booking" });
    await listNotifications(f.sb, "talal");
    await listRequestsWithLocation(f.sb);
    expect(has(f.calls.incidents!, "eq", "status", "open")).toBe(true);
    expect(has(f.calls.review_queue!, "eq", "status", "open")).toBe(true);
    expect(has(f.calls.outbox!, "eq", "kind", "booking")).toBe(true);
    expect(has(f.calls.notifications!, "eq", "alias", "talal")).toBe(true);
    expect(has(f.calls.requests!, "not", "building_id", "is", null)).toBe(true);
  });

  it("throws the PostgREST message on error", async () => {
    const f = fakeSb({ data: null, error: { message: "permission denied" } });
    await expect(listOpenIncidents(f.sb)).rejects.toThrow("permission denied");
  });
});

describe("realtime", () => {
  it("subscribeNotifications filters by alias, passes inserts only, and unsubscribes", () => {
    const f = fakeSb();
    const cb = vi.fn();
    const off = subscribeNotifications(f.sb, "talal", cb);
    const insert = f.handlers.find((h) => h.opts.event === "INSERT")!;
    const update = f.handlers.find((h) => h.opts.event === "UPDATE")!;
    expect(insert.opts).toMatchObject({ table: "notifications", filter: "alias=eq.talal" });
    insert.cb({ new: { id: "n1" } });
    update.cb({ new: { id: "n2" } });
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith({ id: "n1" });
    off();
    expect(f.removed).toHaveLength(1);
  });

  it("subscribeTickets scopes to the office and reports inserts and updates", () => {
    const f = fakeSb();
    const cb = vi.fn();
    subscribeTickets(f.sb, "it", cb);
    expect(f.handlers.every((h) => h.opts.filter === "office=eq.it")).toBe(true);
    f.handlers.forEach((h) => h.cb({ new: { id: "t" } }));
    expect(cb).toHaveBeenCalledTimes(2);
  });

  it("refuses a filter value that could alter the filter", () => {
    const f = fakeSb();
    expect(() => subscribeTickets(f.sb, "it,status=eq.open", vi.fn())).toThrow();
    expect(() => subscribeNotifications(f.sb, "a)or(b", vi.fn())).toThrow();
  });

  it("subscribeRequestsWithLocation drops rows without a building", () => {
    const f = fakeSb();
    const cb = vi.fn();
    subscribeRequestsWithLocation(f.sb, cb);
    f.handlers[0]!.cb({ new: { id: "a", building_id: null } });
    f.handlers[0]!.cb({ new: { id: "b", building_id: "M" } });
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb.mock.calls[0]![0]).toMatchObject({ id: "b" });
  });

  it("subscribeIncidents has no filter (RLS decides)", () => {
    const f = fakeSb();
    subscribeIncidents(f.sb, vi.fn());
    expect(f.handlers.every((h) => !("filter" in h.opts))).toBe(true);
  });
});
