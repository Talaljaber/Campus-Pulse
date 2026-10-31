import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const session = { access_token: "user-jwt-123" };
let signedIn = true;
const profileAlias = "talal";

vi.mock("@/lib/supabase/server", () => ({
  createServerSupabase: async () => ({
    auth: {
      getUser: async () => ({ data: { user: signedIn ? { id: "u1" } : null } }),
      getSession: async () => ({ data: { session: signedIn ? session : null } }),
    },
    from: () => ({
      select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: { alias: profileAlias } }) }) }),
    }),
  }),
}));

import { aiFetch } from "@/lib/ai/client";
import { GET, POST } from "@/app/api/ai/[...path]/route";
import { NextRequest } from "next/server";

const fetchMock = vi.fn();

function req(method: string, path: string, init: { body?: unknown; headers?: Record<string, string> } = {}) {
  return new NextRequest(`http://localhost/api/ai/${path}`, {
    method,
    headers: { "content-type": "application/json", ...init.headers },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}
const ctx = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeEach(() => {
  signedIn = true;
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("AI_SERVICE_URL", "http://ai.test");
  vi.stubEnv("AI_SERVICE_TOKEN", "svc-token-xyz");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("proxy allow-list", () => {
  it.each([
    ["GET", "admin/users"],
    ["POST", "integrations/linear/webhook"],
    ["GET", "triage"],
    ["POST", "triage/abc/clarify/extra"],
    ["GET", "health/../metrics"],
    ["POST", "metrics"],
  ])("rejects %s %s with 404 and never reaches the service", async (method, path) => {
    const handler = method === "GET" ? GET : POST;
    const res = await handler(req(method, path, { body: method === "POST" ? {} : undefined }), ctx(path));
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers 401 without a session on a protected path", async () => {
    signedIn = false;
    const res = await POST(req("POST", "triage", { body: { text: "hi" } }), ctx("triage"));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lets the health probe through without a session", async () => {
    signedIn = false;
    fetchMock.mockResolvedValue(json({ status: "ok" }));
    const res = await GET(req("GET", "health"), ctx("health"));
    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0]!;
    expect((init.headers as Record<string, string>)["X-CP-User-JWT"]).toBeUndefined();
  });
});

describe("proxy forwarding", () => {
  it("never forwards a client-supplied Authorization or X-CP-* header", async () => {
    fetchMock.mockResolvedValue(json({ status: "decided" }));
    await POST(
      req("POST", "triage", {
        body: { text: "wifi down" },
        headers: { authorization: "Bearer attacker", "x-cp-role": "admin", "x-cp-user-jwt": "forged", cookie: "a=b" },
      }),
      ctx("triage"),
    );
    const [url, init] = fetchMock.mock.calls[0]!;
    const headers = init.headers as Record<string, string>;
    expect(url).toBe("http://ai.test/v1/triage");
    expect(headers.Authorization).toBe("Bearer svc-token-xyz");
    expect(headers["X-CP-User-JWT"]).toBe("user-jwt-123");
    expect(Object.keys(headers).map((k) => k.toLowerCase())).not.toContain("x-cp-role");
    expect(JSON.stringify(headers)).not.toContain("attacker");
    expect(JSON.stringify(headers)).not.toContain("forged");
  });

  it("sets student_alias from the profile, overriding the browser's value", async () => {
    fetchMock.mockResolvedValue(json({ status: "decided" }));
    await POST(req("POST", "triage", { body: { text: "x", student_alias: "someone-else" } }), ctx("triage"));
    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(init.body as string)).toEqual({ text: "x", student_alias: profileAlias });
  });

  it("forwards the query string of an allowed path", async () => {
    fetchMock.mockResolvedValue(json({ drop: "today" }));
    await GET(req("GET", "explain/abc-1/counterfactual?drop=today"), ctx("explain/abc-1/counterfactual"));
    expect(fetchMock.mock.calls[0]![0]).toBe("http://ai.test/v1/explain/abc-1/counterfactual?drop=today");
  });

  it("maps an API error body to the same status and a typed body", async () => {
    fetchMock.mockResolvedValue(json({ error: { code: "not_found", message: "Incident not found.", details: { id: "1" } } }, 404));
    const res = await POST(req("POST", "incidents/abc/resolve", { body: {} }), ctx("incidents/abc/resolve"));
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({
      error: { code: "not_found", message: "Incident not found.", details: { id: "1" } },
      waking: false,
    });
  });

  it("maps a fetch timeout to waking: true", async () => {
    fetchMock.mockRejectedValue(new DOMException("timed out", "TimeoutError"));
    const res = await POST(req("POST", "triage", { body: { text: "x" } }), ctx("triage"));
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.waking).toBe(true);
    expect(body.error.code).toBe("ai_waking");
  });
});

describe("aiFetch", () => {
  it("returns data on success and sends the two credentials", async () => {
    fetchMock.mockResolvedValue(json({ ok: 1 }));
    const r = await aiFetch<{ ok: number }>("metrics", { method: "GET", userJwt: "jwt" });
    expect(r).toEqual({ ok: true, data: { ok: 1 } });
    const headers = fetchMock.mock.calls[0]![1].headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer svc-token-xyz");
    expect(headers["X-CP-User-JWT"]).toBe("jwt");
  });

  it("treats an empty 502 as waking but a 503 with the API body as a real error", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 502 }));
    const a = await aiFetch("triage", { method: "POST", body: {}, userJwt: null });
    expect(a).toMatchObject({ ok: false, status: 502, waking: true, code: "ai_waking" });

    fetchMock.mockResolvedValueOnce(json({ error: { code: "store_unavailable", message: "down", details: null } }, 503));
    const b = await aiFetch("triage", { method: "POST", body: {}, userJwt: null });
    expect(b).toMatchObject({ ok: false, status: 503, waking: false, code: "store_unavailable" });
  });

  it("maps a refused connection to network, waking", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const r = await aiFetch("health", { method: "GET", userJwt: null });
    expect(r).toMatchObject({ ok: false, code: "network", waking: true });
  });

  it("reports a missing configuration instead of throwing", async () => {
    vi.stubEnv("AI_SERVICE_URL", "");
    const r = await aiFetch("health", { method: "GET", userJwt: null });
    expect(r).toMatchObject({ ok: false, code: "ai_not_configured", waking: false });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
