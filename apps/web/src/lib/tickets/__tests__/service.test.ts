import { describe, expect, it, vi } from "vitest";
import { mergeActivity } from "@/hooks/useTicketThread";
import { listActivity, listHints } from "@/lib/repos";
import type { AiFail } from "@/lib/ai/result";
import type { Sb } from "@/lib/supabase/types";
import { failMessage } from "../service";
import type { ActivityRow } from "../types";

const fail = (status: number, code: AiFail["code"], error = ""): AiFail => ({ ok: false, status, code, error, details: null, waking: false });

describe("failMessage", () => {
  it("shows the server's own words for a refused transition and our sentence otherwise", () => {
    expect(failMessage(fail(422, "invalid_input", "transition closed -> solved not allowed"))).toEqual({
      kind: "server",
      text: "transition closed -> solved not allowed",
    });
    expect(failMessage(fail(403, "forbidden", "nope"))).toEqual({ kind: "dict", key: "staff.error.forbidden" });
    expect(failMessage(fail(404, "not_found"))).toEqual({ kind: "dict", key: "staff.error.notFound" });
    expect(failMessage(fail(401, "unauthenticated"))).toEqual({ kind: "dict", key: "staff.error.session" });
    expect(failMessage({ ...fail(503, "ai_waking"), waking: true })).toEqual({ kind: "dict", key: "staff.error.waking" });
    expect(failMessage(fail(500, "internal_error"))).toEqual({ kind: "dict", key: "staff.error.generic" });
  });
});

describe("mergeActivity", () => {
  const r = (id: string, at: string, body = ""): ActivityRow =>
    ({ id, created_at: at, body, ticket_id: "t", kind: "comment", visibility: "public", actor_role: "staff" }) as ActivityRow;

  it("adds new rows in time order and replaces a known id instead of duplicating it", () => {
    const base = [r("a", "2026-11-08T10:00:00Z"), r("c", "2026-11-08T12:00:00Z")];
    const next = mergeActivity(base, r("b", "2026-11-08T11:00:00Z"));
    expect(next.map((x) => x.id)).toEqual(["a", "b", "c"]);
    expect(mergeActivity(next, r("b", "2026-11-08T11:00:00Z", "edited")).map((x) => x.body)).toEqual(["", "edited", ""]);
    expect(base).toHaveLength(2);
  });
});

describe("thread and hint reads", () => {
  const sbWith = (calls: unknown[][]) => {
    const builder: unknown = new Proxy(
      {},
      {
        get(_t, prop: string) {
          if (prop === "then") return (res: (v: unknown) => void) => res({ data: [], error: null });
          return (...args: unknown[]) => {
            calls.push([prop, ...args]);
            return builder;
          };
        },
      },
    );
    return { from: vi.fn((table: string) => (calls.push(["from", table]), builder)) } as unknown as Sb;
  };

  it("reads a thread oldest first for one ticket", async () => {
    const calls: unknown[][] = [];
    await listActivity(sbWith(calls), "t1");
    expect(calls).toContainEqual(["from", "ticket_activity"]);
    expect(calls).toContainEqual(["eq", "ticket_id", "t1"]);
    expect(calls).toContainEqual(["order", "created_at", { ascending: true }]);
  });

  it("never selects the embedding column of hints", async () => {
    const calls: unknown[][] = [];
    await listHints(sbWith(calls));
    const select = calls.find((c) => c[0] === "select");
    expect(select?.[1]).toContain("corrected_category");
    expect(select?.[1]).not.toContain("embedding");
    expect(select?.[1]).not.toContain("*");
  });
});
