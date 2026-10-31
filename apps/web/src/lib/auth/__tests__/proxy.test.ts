import { beforeEach, describe, expect, it, vi } from "vitest";

let user: { id: string } | null = null;
let profile: { id: string; role: string; office: string | null; alias: string | null } | null = null;

vi.mock("@supabase/ssr", () => ({
  createServerClient: () => ({
    auth: { getUser: async () => ({ data: { user } }) },
    from: () => ({
      select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: profile, error: null }) }) }),
    }),
  }),
}));

import { NextRequest } from "next/server";
import { proxy } from "@/proxy";

const req = (path: string) => new NextRequest(`http://localhost:3000${path}`);

function setUser(role: string | null) {
  user = role ? { id: "u1" } : null;
  profile = role ? { id: "u1", role, office: role === "staff" ? "it" : null, alias: "x" } : null;
}

async function run(path: string) {
  const res = await proxy(req(path));
  const location = res.headers.get("location");
  return location ? { status: res.status, to: new URL(location).pathname + new URL(location).search } : { status: res.status, to: null };
}

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "http://localhost:54399");
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon");
  setUser(null);
});

describe("proxy redirect matrix (session mocked)", () => {
  it("signed out: / goes to /login", async () => {
    expect(await run("/")).toEqual({ status: 307, to: "/login" });
  });
  it("signed out: /staff goes to /login with next", async () => {
    expect(await run("/staff")).toEqual({ status: 307, to: "/login?next=%2Fstaff" });
  });
  it("signed out: /login passes", async () => {
    expect((await run("/login")).to).toBeNull();
  });
  it("student visiting /lab is redirected to /", async () => {
    setUser("student");
    expect(await run("/lab")).toEqual({ status: 307, to: "/" });
  });
  it("student visiting /staff is redirected to /", async () => {
    setUser("student");
    expect(await run("/staff")).toEqual({ status: 307, to: "/" });
  });
  it("staff on /login goes to /staff, and /lab goes to /staff", async () => {
    setUser("staff");
    expect(await run("/login")).toEqual({ status: 307, to: "/staff" });
    expect(await run("/lab")).toEqual({ status: 307, to: "/staff" });
  });
  it("admin on /login goes to /lab and may open /pulse", async () => {
    setUser("admin");
    expect(await run("/login")).toEqual({ status: 307, to: "/lab" });
    expect((await run("/pulse")).to).toBeNull();
  });
  it("a user without a profile is treated as signed out", async () => {
    user = { id: "u1" };
    profile = null;
    expect(await run("/")).toEqual({ status: 307, to: "/login" });
  });
  it("a profile with an unknown role is treated as signed out", async () => {
    user = { id: "u1" };
    profile = { id: "u1", role: "superuser", office: null, alias: null };
    expect(await run("/staff")).toEqual({ status: 307, to: "/login?next=%2Fstaff" });
  });
});
