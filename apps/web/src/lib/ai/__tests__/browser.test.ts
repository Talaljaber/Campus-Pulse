import { afterEach, describe, expect, it, vi } from "vitest";
import { callAi } from "@/lib/ai/browser";
import { outcomeOf } from "@/lib/ai/health";
import type { HealthResponse } from "@/lib/ai/types";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(res: Response): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));
}

describe("callAi with a 2xx whose body cannot be read", () => {
  it("returns a waking failure instead of a success with null data", async () => {
    // A JSON content type with an empty body: res.json() throws, as it does when the probe timeout
    // cuts the body off mid-read.
    stubFetch(new Response("", { status: 200, headers: { "content-type": "application/json" } }));
    const res = await callAi<HealthResponse>("health");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.waking).toBe(true);
  });

  it("the health probe classifies it as unreachable, never a crash", async () => {
    stubFetch(new Response("", { status: 200, headers: { "content-type": "application/json" } }));
    const res = await callAi<HealthResponse>("health");
    expect(outcomeOf(res)).toBe("unreachable");
  });

  it("still returns the data of a readable 2xx", async () => {
    stubFetch(
      new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    const res = await callAi<{ status: string }>("health");
    expect(res.ok).toBe(true);
    if (res.ok) expect(res.data.status).toBe("ok");
  });
});
