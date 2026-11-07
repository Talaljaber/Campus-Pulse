/**
 * Role-based routing, as pure functions so the redirect matrix is testable without a
 * request object. `src/proxy.ts` calls `decideRoute` after it has read the session.
 */

export type Role = "student" | "staff" | "admin";

export const ROLES: readonly Role[] = ["student", "staff", "admin"];

export function isRole(v: unknown): v is Role {
  return v === "student" || v === "staff" || v === "admin";
}

/** Where each role lands after signing in: students on Home, staff on the queue, admins on the Overview. */
export function homeFor(role: Role): string {
  return role === "student" ? "/" : role === "admin" ? "/admin" : "/staff";
}

/** Paths that need at least staff, and the one that needs admin. */
const STAFF_PATHS = ["/staff", "/pulse", "/outbox"] as const;
const ADMIN_PATHS = ["/admin"] as const;
/** Reachable without a session. `/dev` 404s itself in production. */
const PUBLIC_PATHS = ["/login", "/dev"] as const;

const under = (pathname: string, base: string): boolean => pathname === base || pathname.startsWith(`${base}/`);
const underAny = (pathname: string, bases: readonly string[]): boolean => bases.some((b) => under(pathname, b));

export type RouteDecision = { action: "next" } | { action: "redirect"; to: string };

/**
 * Decides what to do with a page request.
 * - No session: only the public paths pass; the rest go to `/login?next=...`.
 * - Signed in on `/login`: sent to the role's home.
 * - `/staff`, `/pulse`, `/outbox` need staff or admin; `/admin` needs admin. Anyone else goes to their own home.
 * - Everything else (`/`, `/ask`, `/requests`, `/profile` for every signed-in role) passes.
 */
export function decideRoute(pathname: string, role: Role | null): RouteDecision {
  if (role === null) {
    if (underAny(pathname, PUBLIC_PATHS)) return { action: "next" };
    const next = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname)}`;
    return { action: "redirect", to: `/login${next}` };
  }
  if (under(pathname, "/login")) return { action: "redirect", to: homeFor(role) };
  if (underAny(pathname, ADMIN_PATHS) && role !== "admin") return { action: "redirect", to: homeFor(role) };
  if (underAny(pathname, STAFF_PATHS) && role === "student") return { action: "redirect", to: homeFor(role) };
  return { action: "next" };
}

/**
 * Accepts a `?next=` value only when it is a same-origin path. `//host`, `/\host`,
 * absolute URLs and anything not starting with a single `/` fall back to `fallback`.
 */
export function safeNext(next: string | null | undefined, fallback: string): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  if (/[\u0000-\u001f]/.test(next)) return fallback;
  return next;
}
