// @vitest-environment node
// Real Node FormData and File (undici), as in the deployed route handler; jsdom's File does not survive a Request body.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

let signedIn = true;
vi.mock("@/lib/supabase/server", () => ({
  createServerSupabase: async () => ({
    auth: {
      getUser: async () => ({ data: { user: signedIn ? { id: "u1" } : null } }),
      getSession: async () => ({ data: { session: signedIn ? { access_token: "user-jwt-123" } : null } }),
    },
    from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: { alias: "talal" } }) }) }) }),
  }),
}));

import { GET, POST } from "@/app/api/ai/[...path]/route";
import { NextRequest } from "next/server";

const fetchMock = vi.fn();
const req = (method: string, path: string) => new NextRequest(`http://localhost/api/ai/${path}`, { method });
const ctx = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

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

describe("ticket files (multipart upload and signed link)", () => {
  it("forwards a multipart upload untouched with the service credentials", async () => {
    fetchMock.mockResolvedValue(json({ id: "f1" }));
    const form = new FormData();
    form.append("file", new File(["hello"], "note.txt"));
    form.append("internal", "false");
    const request = new NextRequest("http://localhost/api/ai/tickets/abc-1/files", { method: "POST", body: form });
    const res = await POST(request, ctx("tickets/abc-1/files"));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://ai.test/v1/tickets/abc-1/files");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("internal")).toBe("false");
    expect(((init.body as FormData).get("file") as File).size).toBe(5); // the 5 bytes of "hello" arrive intact
    expect(init.headers["Content-Type"]).toBeUndefined(); // fetch adds the multipart boundary
    expect(init.headers.Authorization).toBe("Bearer svc-token-xyz");
    expect(init.headers["X-CP-User-JWT"]).toBe("user-jwt-123");
  });

  it("needs a signed-in user for both calls", async () => {
    signedIn = false;
    const form = new FormData();
    form.append("file", new File(["x"], "a.txt"));
    const up = await POST(new NextRequest("http://localhost/api/ai/tickets/abc-1/files", { method: "POST", body: form }), ctx("tickets/abc-1/files"));
    expect(up.status).toBe(401);
    const link = await GET(req("GET", "files/f1/link"), ctx("files/f1/link"));
    expect(link.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards the link request and returns the signed link", async () => {
    fetchMock.mockResolvedValue(json({ url: "https://storage.example/x", expires_in: 60 }));
    const res = await GET(req("GET", "files/f1/link"), ctx("files/f1/link"));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ url: "https://storage.example/x", expires_in: 60 });
    expect(fetchMock.mock.calls[0]![0]).toBe("http://ai.test/v1/files/f1/link");
    expect(res.headers.get("Cache-Control")).toBe("no-store");
  });
});
