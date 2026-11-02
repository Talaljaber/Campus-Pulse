import { describe, expect, it, vi } from "vitest";
import { getMyProfile, listLiveAnnouncements, listOfficeAnnouncements, listProfiles, subscribeAnnouncements } from "@/lib/repos";
import type { Sb } from "@/lib/supabase/types";

type Call = [method: string, args: unknown[]];

function fakeSb(result: { data: unknown; error: { message: string } | null } = { data: [], error: null }) {
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

describe("announcement reads", () => {
  it("listLiveAnnouncements keeps live rows only: not archived, started, not ended; newest first, 20 at most", async () => {
    const f = fakeSb();
    const now = new Date("2026-11-05T06:05:00Z");
    await listLiveAnnouncements(f.sb, now);
    const c = f.calls.announcements!;
    expect(has(c, "is", "archived_at", null)).toBe(true);
    expect(has(c, "lte", "starts_at", "2026-11-05T06:05:00.000Z")).toBe(true);
    expect(has(c, "or", "ends_at.is.null,ends_at.gt.2026-11-05T06:05:00.000Z")).toBe(true);
    expect(has(c, "order", "starts_at", { ascending: false })).toBe(true);
    expect(has(c, "limit", 20)).toBe(true);
  });

  it("listOfficeAnnouncements filters by office, or reads everything RLS allows for null, archived rows included", async () => {
    const a = fakeSb();
    await listOfficeAnnouncements(a.sb, "it");
    expect(has(a.calls.announcements!, "eq", "office", "it")).toBe(true);
    expect(a.calls.announcements!.some(([m]) => m === "is")).toBe(false);
    const b = fakeSb();
    await listOfficeAnnouncements(b.sb, null);
    expect(b.calls.announcements!.some(([m]) => m === "eq")).toBe(false);
  });

  it("throws the PostgREST error", async () => {
    const f = fakeSb({ data: null, error: { message: "boom" } });
    await expect(listLiveAnnouncements(f.sb, new Date())).rejects.toThrow("boom");
  });

  it("subscribeAnnouncements reports inserts and updates and unsubscribes", () => {
    const f = fakeSb();
    const seen: unknown[] = [];
    const off = subscribeAnnouncements(f.sb, (r) => seen.push(r));
    expect(f.handlers.map((h) => h.opts.event)).toEqual(["INSERT", "UPDATE"]);
    f.handlers[0]!.cb({ new: { id: "a1" } });
    expect(seen).toEqual([{ id: "a1" }]);
    off();
    expect((f.sb.removeChannel as unknown as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1);
  });
});

describe("profile reads", () => {
  it("getMyProfile reads one row by id and never selects demo_inbox", async () => {
    const f = fakeSb({ data: { id: "u1", role: "student" }, error: null });
    expect(await getMyProfile(f.sb, "u1")).toEqual({ id: "u1", role: "student" });
    const c = f.calls.profiles!;
    expect(has(c, "eq", "id", "u1")).toBe(true);
    const select = c.find(([m]) => m === "select")![1][0] as string;
    expect(select).toContain("student_number");
    expect(select).not.toContain("demo_inbox");
  });

  it("listProfiles returns the rows, ordered by role then name", async () => {
    const f = fakeSb({ data: [{ id: "a" }, { id: "b" }], error: null });
    expect(await listProfiles(f.sb)).toHaveLength(2);
    expect(has(f.calls.profiles!, "order", "role")).toBe(true);
  });
});
