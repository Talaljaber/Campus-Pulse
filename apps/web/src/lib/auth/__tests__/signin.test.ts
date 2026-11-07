import { describe, expect, it, vi } from "vitest";
import { roleMatches, signIn } from "@/lib/auth/signin";
import type { Sb } from "@/lib/supabase/types";

function fakeSb(opts: {
  auth: { data: { user: { id: string } | null }; error: { status?: number; message: string } | null } | "throw";
  profile?: { id: string; role: string; office: string | null; alias: string | null } | null;
}) {
  const signOut = vi.fn(async () => ({ error: null }));
  const sb = {
    auth: {
      signInWithPassword: async () => {
        if (opts.auth === "throw") throw new TypeError("fetch failed");
        return opts.auth;
      },
      signOut,
    },
    from: () => ({
      select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: opts.profile ?? null, error: null }) }) }),
    }),
  } as unknown as Sb;
  return { sb, signOut };
}

const ok = { data: { user: { id: "u1" } }, error: null };

describe("signIn", () => {
  it.each([
    ["student", "/"],
    ["staff", "/staff"],
    ["admin", "/admin"],
  ])("routes a %s to %s", async (role, dest) => {
    const { sb } = fakeSb({ auth: ok, profile: { id: "u1", role, office: null, alias: "a" } });
    expect(await signIn(sb, " a@demo.local ", "pw")).toEqual({ ok: true, role, destination: dest });
  });

  it("signs out and reports wrong_role when the role does not fit the button", async () => {
    const student = fakeSb({ auth: ok, profile: { id: "u1", role: "student", office: null, alias: "talal" } });
    expect(await signIn(student.sb, "talal", "pw", null, "staff")).toEqual({ ok: false, reason: "wrong_role" });
    expect(student.signOut).toHaveBeenCalledOnce();
    const staff = fakeSb({ auth: ok, profile: { id: "u1", role: "staff", office: "it", alias: "staff-it" } });
    expect(await signIn(staff.sb, "it", "pw", null, "student")).toEqual({ ok: false, reason: "wrong_role" });
    expect(staff.signOut).toHaveBeenCalledOnce();
  });

  it("accepts staff and admin on the staff button and a student on the student button", async () => {
    for (const [role, as] of [["staff", "staff"], ["admin", "staff"], ["student", "student"]] as const) {
      const { sb, signOut } = fakeSb({ auth: ok, profile: { id: "u1", role, office: null, alias: "a" } });
      expect(await signIn(sb, "a", "pw", null, as)).toMatchObject({ ok: true, role });
      expect(signOut).not.toHaveBeenCalled();
    }
    expect(roleMatches("admin", "student")).toBe(false);
  });

  it("honours a safe next path and ignores an unsafe one", async () => {
    const p = { id: "u1", role: "staff", office: "it", alias: "s" };
    expect(await signIn(fakeSb({ auth: ok, profile: p }).sb, "a", "b", "/pulse")).toMatchObject({ destination: "/pulse" });
    expect(await signIn(fakeSb({ auth: ok, profile: p }).sb, "a", "b", "//evil.example")).toMatchObject({ destination: "/staff" });
  });

  it("reports wrong credentials", async () => {
    const { sb } = fakeSb({ auth: { data: { user: null }, error: { status: 400, message: "Invalid login credentials" } } });
    expect(await signIn(sb, "a", "b")).toEqual({ ok: false, reason: "invalid" });
  });

  it("reports a transport failure as network", async () => {
    expect(await signIn(fakeSb({ auth: "throw" }).sb, "a", "b")).toEqual({ ok: false, reason: "network" });
    const { sb } = fakeSb({ auth: { data: { user: null }, error: { message: "boom" } } });
    expect(await signIn(sb, "a", "b")).toEqual({ ok: false, reason: "network" });
  });

  it("signs out again when the account has no usable profile", async () => {
    const { sb, signOut } = fakeSb({ auth: ok, profile: null });
    expect(await signIn(sb, "a", "b")).toEqual({ ok: false, reason: "no_profile" });
    expect(signOut).toHaveBeenCalled();
  });
});
