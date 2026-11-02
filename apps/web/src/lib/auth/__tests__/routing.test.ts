import { describe, expect, it } from "vitest";
import { decideRoute, homeFor, safeNext, type Role } from "@/lib/auth/routing";

const NEXT = { action: "next" } as const;
const to = (path: string) => ({ action: "redirect", to: path }) as const;

describe("homeFor", () => {
  it("maps each role to its landing page", () => {
    expect(homeFor("student")).toBe("/");
    expect(homeFor("staff")).toBe("/staff");
    expect(homeFor("admin")).toBe("/staff");
  });
});

describe("decideRoute matrix", () => {
  const cases: Array<[string, Role | null, ReturnType<typeof decideRoute>]> = [
    // signed out
    ["/", null, to("/login")],
    ["/staff", null, to("/login?next=%2Fstaff")],
    ["/pulse", null, to("/login?next=%2Fpulse")],
    ["/lab", null, to("/login?next=%2Flab")],
    ["/ask", null, to("/login?next=%2Fask")],
    ["/requests", null, to("/login?next=%2Frequests")],
    ["/profile", null, to("/login?next=%2Fprofile")],
    ["/admin/accounts", null, to("/login?next=%2Fadmin%2Faccounts")],
    ["/login", null, NEXT],
    ["/dev/ui", null, NEXT],
    // student
    ["/", "student", NEXT],
    ["/login", "student", to("/")],
    ["/staff", "student", to("/")],
    ["/pulse", "student", to("/")],
    ["/outbox", "student", to("/")],
    ["/lab", "student", to("/")],
    ["/ask", "student", NEXT],
    ["/requests", "student", NEXT],
    ["/profile", "student", NEXT],
    ["/staff/announcements", "student", to("/")],
    ["/admin/accounts", "student", to("/")],
    // staff
    ["/", "staff", NEXT],
    ["/login", "staff", to("/staff")],
    ["/staff", "staff", NEXT],
    ["/staff/reviews", "staff", NEXT],
    ["/staff/reviews", "student", to("/")],
    ["/staff/reviews", null, to("/login?next=%2Fstaff%2Freviews")],
    ["/pulse", "staff", NEXT],
    ["/outbox", "staff", NEXT],
    ["/lab", "staff", to("/staff")],
    ["/ask", "staff", NEXT],
    ["/requests", "staff", NEXT],
    ["/profile", "staff", NEXT],
    ["/staff/announcements", "staff", NEXT],
    ["/admin/accounts", "staff", to("/staff")],
    ["/admin", "staff", to("/staff")],
    // admin
    ["/", "admin", NEXT],
    ["/login", "admin", to("/staff")],
    ["/ask", "admin", NEXT],
    ["/requests", "admin", NEXT],
    ["/profile", "admin", NEXT],
    ["/staff/announcements", "admin", NEXT],
    ["/admin/accounts", "admin", NEXT],
    ["/staff", "admin", NEXT],
    ["/pulse", "admin", NEXT],
    ["/outbox", "admin", NEXT],
    ["/lab", "admin", NEXT],
    ["/lab/anything", "admin", NEXT],
  ];
  it.each(cases)("%s as %s", (path, role, expected) => {
    expect(decideRoute(path, role)).toEqual(expected);
  });

  it("does not treat a look-alike prefix as a protected path", () => {
    expect(decideRoute("/staffing", "student")).toEqual(NEXT);
    expect(decideRoute("/laboratory", "student")).toEqual(NEXT);
  });
});

describe("safeNext", () => {
  it("keeps same-origin paths", () => {
    expect(safeNext("/staff?x=1", "/")).toBe("/staff?x=1");
  });
  it.each(["//evil.example", "/\\evil.example", "https://evil.example", "javascript:alert(1)", "staff", "", "/a\nb"])(
    "rejects %j",
    (v) => {
      expect(safeNext(v, "/fallback")).toBe("/fallback");
    },
  );
  it("falls back for null and undefined", () => {
    expect(safeNext(null, "/x")).toBe("/x");
    expect(safeNext(undefined, "/x")).toBe("/x");
  });
});
